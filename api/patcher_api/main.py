import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from sqlalchemy.engine.url import make_url
from starlette.responses import Response

from patcher_api.config import get_settings
from patcher_api.db import get_engine, get_session_maker, init_db
from patcher_api.routes import apps
from patcher_api.seed import seed_database

log = logging.getLogger(__name__)

# Routes whose responses are derived from catalog data and benefit from
# ETag + Cache-Control headers. Other routes (admin, health) bypass.
_CACHEABLE_PATH_PREFIX = "/apps"

# Public cache TTL applied to /apps* responses. 5 minutes is generous
# enough for Cloudflare to absorb the bulk of traffic between catalog
# refreshes, short enough that a manually-triggered refresh propagates
# quickly. ``stale-while-revalidate`` keeps responses warm for clients
# during the brief window when a deploy invalidates the ETag.
_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=3600"


def _catalog_db_path() -> Path | None:
    """
    Resolve the on-disk path of the SQLite catalog DB from the configured
    database URL. Returns ``None`` for in-memory databases (tests use
    ``sqlite+aiosqlite:///:memory:``).
    """
    url = make_url(get_settings().database_url)
    if not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def _hash_catalog_file(path: Path) -> str:
    """One-shot SHA-256 of the catalog DB file, ~1 second for a 65 MB DB."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()

    if get_settings().seed_on_startup:
        async with get_session_maker()() as session:
            await seed_database(session)

    # Compute the catalog hash once per startup. The catalog-refresh
    # systemd unit restarts patcher-api.service after its ingest run
    # completes, so this hash is current for the lifetime of the process.
    # Used as the ETag for ``/apps*`` responses; clients can revalidate
    # without re-downloading the body.
    catalog_path = _catalog_db_path()
    if catalog_path is not None and catalog_path.exists():
        app.state.catalog_sha = _hash_catalog_file(catalog_path)
        log.info("Catalog SHA-256 on startup: %s", app.state.catalog_sha)
    else:
        # In-memory DB (tests), or first boot before any catalog has been
        # uploaded. Middleware no-ops when this is unset.
        app.state.catalog_sha = None

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
    Tag catalog responses with a weak ETag derived from the catalog file's
    SHA-256, plus a public ``Cache-Control`` header that authorizes
    Cloudflare and well-behaved clients to cache.

    The catalog file's hash changes exactly when the data changes, never
    otherwise, so it's a perfect cache key: an ``If-None-Match`` from a
    revalidating client short-circuits to 304 instantly between deploys,
    and Cloudflare can serve the cached body across many users without
    hitting the origin. The combined effect typically takes 90%+ of read
    traffic off the origin.

    Scoped to GET requests against ``/apps*``. /health and POSTs bypass.
    """
    if request.method != "GET" or not request.url.path.startswith(_CACHEABLE_PATH_PREFIX):
        return await call_next(request)

    catalog_sha = getattr(request.app.state, "catalog_sha", None)
    if not catalog_sha:
        # No hash yet (test transport without lifespan, or first boot
        # pre-catalog). Skip cache headers; let the response flow through.
        return await call_next(request)

    etag = f'W/"{catalog_sha}"'

    # 304 short-circuit. Returning early means the route function isn't
    # even called, saving the DB read entirely. ``If-None-Match`` per RFC
    # 7232 accepts either ``*`` (wildcard match) or a comma-separated list
    # of ETags; both forms must match the current ETag to short-circuit.
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
