"""
Origin validation middleware for the Patcher MCP endpoint.

MCP spec rev 2025-06-18 has a security MUST on Streamable HTTP servers:
*"Servers MUST validate the Origin header on all incoming connections to
prevent DNS rebinding attacks."* For a hosted-with-TLS server the practical
attack surface is small (DNS rebinding mostly bites localhost servers), but
the spec is the spec and this middleware is the spec-mandated defense.

Browser clients send an ``Origin`` header on cross-origin requests; we
check it against an allowlist configured via :class:`patcher_api.config.Settings`.
Native MCP clients (Claude Desktop, Cursor, the ``fastmcp`` CLI) typically
don't send an Origin header at all because it's a browser security mechanism;
for those we let the request through.
"""

import logging

from starlette.types import ASGIApp, Receive, Scope, Send

from patcher_api.config import get_settings

log = logging.getLogger(__name__)


class OriginValidationMiddleware:
    """
    Reject HTTP requests whose ``Origin`` header is present and not in the
    catalog's allowlist; pass everything else through.

    The allowlist is read from :func:`get_settings` on each request rather
    than baked in at startup so tests can monkeypatch the settings without
    rebuilding the ASGI app. Per-request cost is negligible because
    ``get_settings`` is ``lru_cache``-d.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # ASGI scope headers are a list of (bytes, bytes) tuples; building the
        # dict here is fine because headers are small and we touch one value.
        headers = dict(scope.get("headers", []))
        origin_bytes = headers.get(b"origin")

        # Native clients send no Origin; the MUST targets browser requests, so absent the header there's nothing to validate.
        if origin_bytes is None:
            await self.app(scope, receive, send)
            return

        origin = origin_bytes.decode("latin-1")
        allowed = frozenset(get_settings().mcp_allowed_origins)
        if origin in allowed:
            await self.app(scope, receive, send)
            return

        log.warning("Rejected MCP request: origin %r not in allowlist", origin)
        await self._send_403(send)

    async def _send_403(self, send: Send) -> None:
        body = b'{"error":"Origin not allowed"}'
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
