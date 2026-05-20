"""
Tests for the admin endpoints.

Exercises the catalog-upload endpoint end-to-end: deploy-token auth (must
be a deploy token specifically, not a user token), size cap, SHA-256
integrity check, atomic-rename semantics, cleanup on failure.

Incoming-dir is monkeypatched to a per-test tmp_path so the tests can run
without writing under ``/var/lib/patcher-api/``.
"""

import hashlib
import secrets
from pathlib import Path

import pytest
import pytest_asyncio
from patcher_api.auth import hash_token
from patcher_api.config import get_settings
from patcher_api.models.deploy_token import DeployToken


@pytest_asyncio.fixture
async def deploy_token(test_session) -> str:
    """Mint a fresh deploy token in the test DB and return the plaintext."""
    plaintext = secrets.token_urlsafe(32)
    test_session.add(DeployToken(user_id="deploy-test", token_hash=hash_token(plaintext)))
    await test_session.commit()
    return plaintext


@pytest.fixture
def incoming_dir(tmp_path, monkeypatch) -> Path:
    """Override the upload landing directory to a per-test tmp path."""
    target = tmp_path / "incoming"
    target.mkdir()
    # Reach into the cached Settings instance and rewrite the attribute. The
    # endpoint reads ``get_settings().incoming_dir`` at request time so the
    # override sticks for the duration of the test.
    monkeypatch.setattr(get_settings(), "incoming_dir", target)
    return target


@pytest.mark.asyncio
async def test_upload_returns_401_without_auth(client, incoming_dir):
    response = await client.post(
        "/admin/catalog/upload",
        content=b"any body",
    )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_upload_accepts_deploy_token_and_stages_file(client, deploy_token, incoming_dir):
    body = b"\x00\x01\x02 SQLite-shaped bytes \x03\x04\x05"
    expected_sha = hashlib.sha256(body).hexdigest()

    response = await client.post(
        "/admin/catalog/upload",
        content=body,
        headers={
            "Authorization": f"Bearer {deploy_token}",
            "Content-Type": "application/octet-stream",
            "X-Catalog-SHA256": expected_sha,
        },
    )

    assert response.status_code == 200
    body_json = response.json()
    assert body_json["bytes_received"] == len(body)
    assert body_json["sha256"] == expected_sha

    # File landed at the watched path. No stray .tmp remains.
    final = incoming_dir / "patcher_api.db"
    assert final.exists()
    assert final.read_bytes() == body
    assert not (incoming_dir / "patcher_api.db.tmp").exists()


@pytest.mark.asyncio
async def test_upload_rejects_sha256_mismatch(client, deploy_token, incoming_dir):
    body = b"some bytes"
    wrong_sha = "0" * 64  # length-correct but won't match

    response = await client.post(
        "/admin/catalog/upload",
        content=body,
        headers={
            "Authorization": f"Bearer {deploy_token}",
            "Content-Type": "application/octet-stream",
            "X-Catalog-SHA256": wrong_sha,
        },
    )

    assert response.status_code == 400
    assert "SHA256" in response.json()["detail"] or "sha256" in response.json()["detail"].lower()
    # No partial artifact left behind in the staging area
    assert not (incoming_dir / "patcher_api.db.tmp").exists()
    assert not (incoming_dir / "patcher_api.db").exists()


@pytest.mark.asyncio
async def test_upload_rejects_oversized_via_content_length(
    client, deploy_token, incoming_dir, monkeypatch
):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 100)

    response = await client.post(
        "/admin/catalog/upload",
        content=b"x" * 200,
        headers={
            "Authorization": f"Bearer {deploy_token}",
            "Content-Type": "application/octet-stream",
        },
    )

    assert response.status_code == 413
    assert not (incoming_dir / "patcher_api.db.tmp").exists()


@pytest.mark.asyncio
async def test_upload_works_without_sha_header(client, deploy_token, incoming_dir):
    """The SHA-256 header is optional; without it the body is still hashed
    and the staged file is still produced."""
    body = b"contents"
    expected_sha = hashlib.sha256(body).hexdigest()

    response = await client.post(
        "/admin/catalog/upload",
        content=body,
        headers={
            "Authorization": f"Bearer {deploy_token}",
            "Content-Type": "application/octet-stream",
        },
    )

    assert response.status_code == 200
    assert response.json()["sha256"] == expected_sha
    assert (incoming_dir / "patcher_api.db").read_bytes() == body


@pytest.mark.asyncio
async def test_upload_revoked_deploy_token_rejected(
    client, deploy_token, test_session, incoming_dir
):
    """A deploy token that has been revoked no longer authorizes uploads."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    # Revoke the token we just minted
    token_row = await test_session.scalar(
        select(DeployToken).where(DeployToken.token_hash == hash_token(deploy_token))
    )
    token_row.revoked_at = datetime.now(UTC)
    await test_session.commit()

    response = await client.post(
        "/admin/catalog/upload",
        content=b"anything",
        headers={"Authorization": f"Bearer {deploy_token}"},
    )
    assert response.status_code == 401
    assert "revoked" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_expired_deploy_token_rejected(client, test_session, incoming_dir):
    """A deploy token past its ``expires_at`` is rejected at the auth boundary.

    Covers the Phase 3 ``DeployToken.expires_at`` column. Tokens minted with
    a past expiration must surface a 401, not a 200.
    """
    from datetime import UTC, datetime, timedelta

    plaintext = secrets.token_urlsafe(32)
    test_session.add(
        DeployToken(
            user_id="expired-test",
            token_hash=hash_token(plaintext),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    await test_session.commit()

    response = await client.post(
        "/admin/catalog/upload",
        content=b"anything",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()
    # No artifact written when auth fails up-front
    assert not (incoming_dir / "patcher_api.db.tmp").exists()
    assert not (incoming_dir / "patcher_api.db").exists()


@pytest.mark.asyncio
async def test_upload_streaming_cap_enforced_without_content_length(
    client, deploy_token, incoming_dir, monkeypatch
):
    """Content-Length is advisory; the streaming check is the actual gate.

    A client that omits Content-Length (or lies about it) still cannot
    upload more than ``max_upload_bytes`` worth of body. The cap fires
    during streaming and the partial ``.tmp`` is cleaned up.
    """
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 100)

    # Stream the body via a generator so httpx omits Content-Length and
    # the server can't reject up-front; it has to enforce the cap mid-stream.
    async def streamer():
        for _ in range(20):  # 20 * 50 bytes = 1000 > 100-byte cap
            yield b"x" * 50

    response = await client.post(
        "/admin/catalog/upload",
        content=streamer(),
        headers={
            "Authorization": f"Bearer {deploy_token}",
            "Content-Type": "application/octet-stream",
        },
    )

    assert response.status_code == 413
    # Partial file from the streaming write must be cleaned up; otherwise
    # a future upload could be confused by stale partial bytes.
    assert not (incoming_dir / "patcher_api.db.tmp").exists()
    # The cap fires mid-stream before the atomic rename, so no final file
    # should ever exist either.
    assert not (incoming_dir / "patcher_api.db").exists()
