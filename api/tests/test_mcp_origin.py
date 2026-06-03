"""
Tests for the MCP endpoint's Origin validation middleware.

These exercise the HTTP path through FastAPI's mount (using an
``ASGITransport``) rather than the in-process MCP Client, because origin
validation only happens on real HTTP traffic. The MCP handshake's success
is incidental: we're asserting on the status code the middleware produces,
not the JSON-RPC response.

The ``mcp_http_client`` fixture explicitly enters the MCP's lifespan context
because ``ASGITransport`` doesn't run ASGI lifespan events on its own, and
the MCP session manager's task group needs to be running for the MCP layer
to dispatch requests cleanly. We skip the full FastAPI lifespan deliberately,
since that would touch the production DB instead of the test engine.

Requests target ``/mcp/`` (with trailing slash) rather than ``/mcp`` because
FastAPI's mount routing 307-redirects bare ``/mcp`` to ``/mcp/`` before the
sub-app's middleware stack runs. Posting directly to ``/mcp/`` exercises
the middleware as it actually fires in production (where MCP clients follow
the redirect transparently).
"""

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from patcher_api.db import get_session
from patcher_api.main import app as fastapi_app
from patcher_api.mcp import mcp_app
from sqlalchemy.ext.asyncio import AsyncSession

_INIT_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0.1"},
    },
}

_INIT_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-06-18",
}


@pytest_asyncio.fixture
async def mcp_http_client(test_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """
    AsyncClient against the FastAPI app with the MCP session manager up.

    Reaching the MCP layer requires the session manager's task group to be
    running, which only happens inside the MCP lifespan context. We skip
    the full FastAPI lifespan (it would init/seed the production DB) and
    just enter the MCP portion directly.
    """

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield test_session

    fastapi_app.dependency_overrides[get_session] = override_get_session
    # LifespanManager on mcp_app (not fastapi_app) initializes just the MCP
    # session manager via proper ASGI lifespan messages, with the task-scope
    # discipline anyio requires. The full FastAPI lifespan would init+seed the
    # production DB; we want only the MCP startup.
    async with LifespanManager(mcp_app):
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app),
            base_url="http://test",
        ) as ac:
            yield ac
    fastapi_app.dependency_overrides.clear()


def _configure_origins(monkeypatch, origins: list[str]) -> None:
    """Point the middleware's ``get_settings`` at a known allowlist (it's lru-cached)."""
    monkeypatch.setattr(
        "patcher_api.mcp.middleware.get_settings",
        lambda: SimpleNamespace(mcp_allowed_origins=origins),
    )


@pytest.mark.asyncio
async def test_request_without_origin_header_passes(mcp_http_client):
    """
    Native MCP clients (Claude Desktop, Cursor, the fastmcp CLI) don't send
    an Origin header. The middleware lets them through.
    """
    response = await mcp_http_client.post("/mcp/", json=_INIT_REQUEST, headers=_INIT_HEADERS)
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_request_with_allowed_origin_passes(mcp_http_client, monkeypatch):
    """Browser request from an allowlisted origin reaches the MCP layer."""
    _configure_origins(monkeypatch, ["https://claude.ai"])
    response = await mcp_http_client.post(
        "/mcp/",
        json=_INIT_REQUEST,
        headers={**_INIT_HEADERS, "Origin": "https://claude.ai"},
    )
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_request_with_disallowed_origin_returns_403(mcp_http_client, monkeypatch):
    """
    Browser request from a non-allowlisted origin is rejected by the
    middleware before the MCP layer runs, with a JSON error body.
    """
    _configure_origins(monkeypatch, ["https://claude.ai"])
    response = await mcp_http_client.post(
        "/mcp/",
        json=_INIT_REQUEST,
        headers={**_INIT_HEADERS, "Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert response.json() == {"error": "Origin not allowed"}


@pytest.mark.asyncio
async def test_empty_origin_header_is_rejected(mcp_http_client, monkeypatch):
    """
    An empty-string Origin is a *present* header that doesn't match the
    allowlist; the middleware treats it as a disallowed origin, not as
    absent. This avoids a class of bypass where a malicious page sends
    ``Origin: `` to slip past the check.
    """
    _configure_origins(monkeypatch, ["https://claude.ai"])
    response = await mcp_http_client.post(
        "/mcp/",
        json=_INIT_REQUEST,
        headers={**_INIT_HEADERS, "Origin": ""},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_allowlist_override_switches_which_origins_pass(mcp_http_client, monkeypatch):
    """
    Changing the configured allowlist via settings switches which origins
    are accepted on subsequent requests, because the middleware reads
    settings on each request (not at startup).
    """
    _configure_origins(monkeypatch, ["https://custom.example"])

    rejected = await mcp_http_client.post(
        "/mcp/",
        json=_INIT_REQUEST,
        headers={**_INIT_HEADERS, "Origin": "https://claude.ai"},
    )
    assert rejected.status_code == 403

    accepted = await mcp_http_client.post(
        "/mcp/",
        json=_INIT_REQUEST,
        headers={**_INIT_HEADERS, "Origin": "https://custom.example"},
    )
    assert accepted.status_code != 403
