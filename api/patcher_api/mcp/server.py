"""
FastMCP server instance for the Patcher catalog.

The ``mcp`` instance holds the tool registry. ``mcp_app`` is the Starlette
ASGI application returned by :meth:`FastMCP.http_app` — that's what
:mod:`patcher_api.main` mounts at ``/mcp``. Stateless HTTP + JSON-response
mode fits a read-only catalog facade: each request is independent, no
per-client session state, no streaming.

``path="/"`` is intentional. The default ``http_app()`` mounts its endpoint
at ``/mcp`` inside its own Starlette router; pairing that with FastAPI's
``app.mount("/mcp", mcp_app)`` would produce ``/mcp/mcp``. Setting the inner
path to ``/`` keeps the public URL clean.

fastmcp's ``http_app()`` returns a ``StarletteWithLifespan`` that owns the
session manager's lifespan internally. ``main.py`` composes it into the
FastAPI parent lifespan via ``mcp_app.router.lifespan_context(app)`` so the
session manager starts and stops alongside the API's own startup hooks.
"""

from fastmcp import FastMCP
from starlette.middleware import Middleware

from patcher_api.mcp.middleware import OriginValidationMiddleware

mcp = FastMCP(
    "Patcher",
    instructions=(
        "Read-only access to the Patcher community catalog of macOS app "
        "patching metadata. Use these tools to query app coverage, fetch "
        "individual app details, and summarize the catalog's state."
    ),
)

mcp_app = mcp.http_app(
    path="/",
    stateless_http=True,
    json_response=True,
    # MCP spec MUST: validate Origin (DNS rebinding) against PATCHER_API_MCP_ALLOWED_ORIGINS; no-Origin clients bypass.
    middleware=[Middleware(OriginValidationMiddleware)],
)
