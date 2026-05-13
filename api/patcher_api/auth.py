"""Bearer-token authentication for the Patcher API.

Tokens are hashed with SHA-256 at rest; only the hash is stored in the
``tokens`` table. The plaintext is shown once at grant time (see
``scripts/grant_token.py``) and never persisted server-side.

Returns RFC 7235-compliant 401s for missing/invalid/revoked credentials with
the ``WWW-Authenticate: Bearer`` header set. FastAPI's default
:class:`~fastapi.security.HTTPBearer` returns 403 for missing headers, which
is wrong per RFC 7235 — hence ``auto_error=False`` and manual handling.
"""

import hashlib

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.db import get_session
from patcher_api.models.token import Token

bearer_scheme = HTTPBearer(auto_error=False)


def hash_token(plaintext: str) -> str:
    """SHA-256 hash a plaintext token for storage and comparison."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> Token:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = await session.scalar(
        select(Token).where(Token.token_hash == hash_token(credentials.credentials))
    )

    if token is None or token.revoked_at is not None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token
