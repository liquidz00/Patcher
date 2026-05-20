"""
Bearer-token authentication for Patcher API admin endpoints.

The catalog (``/apps*``) is public — no token required. Only admin
endpoints (``/admin/*``) authenticate, against a dedicated
``deploy_tokens`` table separate from any user concept.

Deploy tokens are hashed with SHA-256 at rest; only the hash is stored.
The plaintext is shown once at grant time (see
``scripts/grant_deploy_token.py``) and never persisted server-side.

Returns RFC 7235-compliant 401s for missing/invalid/revoked credentials
with the ``WWW-Authenticate: Bearer`` header set. FastAPI's default
:class:`~fastapi.security.HTTPBearer` returns 403 for missing headers,
which is wrong per RFC 7235 — hence ``auto_error=False`` and manual
handling.
"""

import hashlib
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.db import get_session
from patcher_api.models.deploy_token import DeployToken

bearer_scheme = HTTPBearer(auto_error=False)


def hash_token(plaintext: str) -> str:
    """SHA-256 hash a plaintext token for storage and comparison."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


async def get_current_deploy_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> DeployToken:
    """
    Bearer-token auth scoped to the ``deploy_tokens`` table.

    Use as a FastAPI ``Depends()`` on admin-only endpoints (catalog upload,
    future privileged operations). A valid user token from the user-facing
    ``tokens`` table does **not** satisfy this dependency. The two tables
    are independent so revoking one class of credential doesn't affect the
    other, and a compromised user token can't be used to pivot to admin.

    Returns the matching :class:`DeployToken` row on success. RFC 7235-
    compliant 401 with ``WWW-Authenticate: Bearer`` header on missing,
    invalid, or revoked credentials (mirroring :func:`get_current_user`).
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = await session.scalar(
        select(DeployToken).where(DeployToken.token_hash == hash_token(credentials.credentials))
    )

    if token is None or token.revoked_at is not None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked deploy token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Expiry. ``expires_at = NULL`` is treated as "never expires" so rows
    # minted before this column existed continue to work; new tokens get a
    # 90-day default from the grant script.
    #
    # SQLite stores DateTime(timezone=True) as TEXT and some driver/dialect
    # combos return offset-naive datetimes on read. Normalize to UTC so the
    # comparison doesn't blow up with `can't compare offset-naive and
    # offset-aware datetimes`.
    if token.expires_at is not None:
        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise HTTPException(
                status_code=401,
                detail="Deploy token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return token
