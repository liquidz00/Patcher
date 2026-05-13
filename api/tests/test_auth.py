"""
Bearer-token auth tests.

Coverage for the three failure modes (missing, invalid, revoked) plus a
positive case using the pre-authorized ``client`` fixture from conftest.
``/health`` stays public and is exercised separately in test_health.
"""

from datetime import UTC, datetime

import pytest
from patcher_api.auth import hash_token
from patcher_api.models.token import Token
from sqlalchemy import select


@pytest.mark.asyncio
async def test_protected_route_rejects_request_without_auth_header(unauth_client):
    response = await unauth_client.get("/apps")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "Missing Authorization header" in response.json()["detail"]


@pytest.mark.asyncio
async def test_protected_route_rejects_gibberish_token(unauth_client):
    unauth_client.headers["Authorization"] = "Bearer not-a-real-token"
    response = await unauth_client.get("/apps")

    assert response.status_code == 401
    assert "Invalid or revoked token" in response.json()["detail"]


@pytest.mark.asyncio
async def test_protected_route_rejects_revoked_token(unauth_client, test_session, valid_token):
    """Revoking a previously-valid token immediately blocks subsequent requests."""
    token = await test_session.scalar(
        select(Token).where(Token.token_hash == hash_token(valid_token))
    )
    token.revoked_at = datetime.now(UTC)
    await test_session.commit()

    unauth_client.headers["Authorization"] = f"Bearer {valid_token}"
    response = await unauth_client.get("/apps")

    assert response.status_code == 401
    assert "Invalid or revoked token" in response.json()["detail"]


@pytest.mark.asyncio
async def test_protected_route_accepts_valid_token(client):
    """The ``client`` fixture is already authorized — sanity check it works."""
    response = await client.get("/apps")
    assert response.status_code == 200
    assert len(response.json()) > 0


@pytest.mark.asyncio
async def test_health_endpoint_does_not_require_auth(unauth_client):
    """``/health`` is intentionally public (load balancer probes, etc.)."""
    response = await unauth_client.get("/health")
    assert response.status_code == 200
