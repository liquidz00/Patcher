"""
Mint a deploy token authorizing privileged catalog-deployment operations.

Usage::

    uv run python api/scripts/grant_deploy_token.py github-actions-runner

The plaintext is printed once to stdout. Store securely (1Password, GitHub
Actions secret, etc). Only the SHA-256 hash is stored in the database.

Distinct from the user-facing :mod:`scripts.grant_token`. Deploy tokens
authorize the ``/admin/catalog/upload`` endpoint (and any future privileged
admin endpoints). They do **not** authorize user-facing routes; a
compromised user token cannot pivot to the deploy scope and vice versa.

To revoke a deploy token later::

    sqlite3 /var/lib/patcher-api/patcher_api.db \\
      "UPDATE deploy_tokens SET revoked_at = CURRENT_TIMESTAMP WHERE user_id = '<user>';"
"""

import asyncio
import secrets
import sys

from patcher_api.auth import hash_token
from patcher_api.db import get_session_maker, init_db
from patcher_api.models.deploy_token import DeployToken


async def grant_deploy_token(user_id: str) -> str:
    await init_db()

    plaintext = secrets.token_urlsafe(32)

    async with get_session_maker()() as session:
        session.add(DeployToken(user_id=user_id, token_hash=hash_token(plaintext)))
        await session.commit()

    return plaintext


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <user_id>", file=sys.stderr)
        sys.exit(1)

    user_id = sys.argv[1]
    plaintext = asyncio.run(grant_deploy_token(user_id))

    print()
    print(f"Deploy token granted for '{user_id}':")
    print(f"  {plaintext}")
    print()
    print("Store this securely (GitHub Actions secret, 1Password, etc.)")
    print("It will not be shown again.")


if __name__ == "__main__":
    main()
