"""FastAPI application entry point: wires the REST routes, the MCP server, and startup."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from starlette.responses import Response

from patcher_api.catalog import recompute_catalog_version
from patcher_api.config import get_settings
from patcher_api.db import get_engine, get_session_maker
from patcher_api.mcp import mcp_app
from patcher_api.routes import admin, apps, stats
from patcher_api.seed import seed_database

log = logging.getLogger(__name__)

# Only /apps* responses carry ETag and Cache-Control; other routes bypass.
_CACHEABLE_PATH_PREFIX = "/apps"

# Public TTL for /apps*: long enough for Cloudflare to absorb reads, short enough that a refresh propagates.
_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=3600"

# Crawler-readable front door served at ``/``; keeps URL-categorization off a bare 404.
_LANDING_PAGE = Path(__file__).parent / "static" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Schema is owned by Alembic (`alembic upgrade head`, run at deploy); the
    # service assumes an already-migrated DB and never creates tables itself.
    if get_settings().seed_on_startup:
        async with get_session_maker()() as session:
            await seed_database(session)

    # Catalog ETag token, recomputed once per startup (the refresh unit restarts us after each ingest).
    # ``None`` (empty catalog, or first boot pre-catalog) makes the cache middleware a no-op.
    app.state.catalog_version = None
    async with get_session_maker()() as session:
        token = await recompute_catalog_version(app, session)
    if token is not None:
        log.info("Catalog version token on startup: %s", token)

    # app.mount doesn't run a child app's lifespan, so enter fastmcp's explicitly for the serving window.
    async with mcp_app.router.lifespan_context(app):
        yield

    await get_engine().dispose()


app = FastAPI(
    title="Patcher API",
    description="Community catalog of macOS app patching metadata.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def catalog_etag(request: Request, call_next):
    """
    Tag catalog responses with a weak ETag derived from the catalog version
    token, plus a public ``Cache-Control`` header that authorizes Cloudflare
    and well-behaved clients to cache.

    The version token changes exactly when the data changes, never otherwise,
    so it's a perfect cache key: an ``If-None-Match`` from a revalidating
    client short-circuits to 304 instantly between deploys, and Cloudflare can
    serve the cached body across many users without hitting the origin. The
    combined effect typically takes 90%+ of read traffic off the origin.

    Scoped to GET requests against ``/apps*``. /health and POSTs bypass.
    """
    if request.method != "GET" or not request.url.path.startswith(_CACHEABLE_PATH_PREFIX):
        return await call_next(request)

    catalog_version = getattr(request.app.state, "catalog_version", None)
    if not catalog_version:
        # No token yet (test transport, or first boot pre-catalog); skip cache headers.
        return await call_next(request)

    etag = f'W/"{catalog_version}"'

    # 304 short-circuit skips the route and its DB read. If-None-Match is ``*`` or a comma-list per RFC 7232.
    if_none_match = request.headers.get("if-none-match")
    if if_none_match:
        candidates = [c.strip() for c in if_none_match.split(",")]
        if "*" in candidates or etag in candidates:
            return Response(
                status_code=304,
                headers={"ETag": etag, "Cache-Control": _CACHE_CONTROL},
            )

    response = await call_next(request)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return response


app.include_router(apps.router)
app.include_router(admin.router)
app.include_router(stats.router)

# MCP over Streamable HTTP; Cloudflare Tunnel maps mcp.patcherctl.dev to this mount.
app.mount("/mcp", mcp_app)


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(_LANDING_PAGE)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
