"""Mint a bearer token for an authorized API consumer.

Usage::

    uv run python api/scripts/grant_token.py alice

The plaintext token is printed once to stdout — share via 1Password or your
team's password manager. Only the SHA-256 hash is stored in the database.

To revoke a token later, ``UPDATE tokens SET revoked_at = CURRENT_TIMESTAMP
WHERE user_id = '<user>';`` directly against the SQLite file.
"""

import asyncio
import secrets
import sys

from patcher_api.auth import hash_token
from patcher_api.db import get_session_maker, init_db
from patcher_api.models.token import Token


async def grant_token(user_id: str) -> str:
    await init_db()

    plaintext = secrets.token_urlsafe(32)

    async with get_session_maker()() as session:
        session.add(Token(user_id=user_id, token_hash=hash_token(plaintext)))
        await session.commit()

    return plaintext


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <user_id>", file=sys.stderr)
        sys.exit(1)

    user_id = sys.argv[1]
    plaintext = asyncio.run(grant_token(user_id))

    print()
    print(f"Token granted for '{user_id}':")
    print(f"  {plaintext}")
    print()
    print("Store this securely (1Password, etc.) — it will not be shown again.")


if __name__ == "__main__":
    main()
