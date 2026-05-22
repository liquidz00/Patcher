"""
Mint a deploy token authorizing privileged catalog-deployment operations.

Usage::

    uv run python api/scripts/grant_deploy_token.py github-actions-runner

    # Custom expiry (default: 90 days from now):
    uv run python api/scripts/grant_deploy_token.py runner --expires-in-days 30

    # Never expires (use sparingly):
    uv run python api/scripts/grant_deploy_token.py runner --no-expiry

    # Explicit DB target (overrides PATCHER_API_DATABASE_URL):
    uv run python api/scripts/grant_deploy_token.py runner \\
        --database-url "sqlite+aiosqlite:////var/lib/patcher-api/patcher_api.db"

The plaintext is printed once to stdout. Store securely (1Password, GitHub
Actions secret, etc). Only the SHA-256 hash is stored in the database.

The script automatically reads ``/etc/patcher-api/env`` at startup via
the same pydantic-settings machinery the API service uses, so on the
Patcher API server you don't need to source anything or pass any flags
to hit the live DB — provided the user running the script can read
that file (typically the ``patcher`` user; run with ``sudo -u patcher``).
``--database-url`` and ``PATCHER_API_DATABASE_URL`` remain available as
overrides for local testing or non-standard setups. The warning at the
bottom of this docstring still fires when the resolved DB path is
relative, which means none of the sources had a value.

Distinct from the user-facing :mod:`scripts.grant_token`. Deploy tokens
authorize the ``/admin/catalog/upload`` endpoint (and any future
privileged admin endpoints). They do **not** authorize user-facing
routes; a compromised user token cannot pivot to the deploy scope and
vice versa.

To revoke a deploy token later::

    sqlite3 /var/lib/patcher-api/patcher_api.db \\
      "UPDATE deploy_tokens SET revoked_at = CURRENT_TIMESTAMP WHERE user_id = '<user>';"
"""

import argparse
import asyncio
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta

from patcher_api.auth import hash_token
from patcher_api.config import get_settings
from patcher_api.db import get_session_maker, init_db
from patcher_api.models.deploy_token import DEFAULT_LIFETIME, DeployToken
from sqlalchemy.engine import make_url


def _resolve_database_url(cli_url: str | None) -> tuple[str, bool]:
    """Resolve which DB URL to use and whether it landed on the relative fallback.

    The actual lookup hierarchy lives in :class:`patcher_api.config.Settings`
    (CLI flag overrides shell env overrides ``/etc/patcher-api/env`` overrides
    ``.env`` overrides the relative default). This wrapper handles the CLI
    flag side and detects the "relative-path fallback" case so the caller can
    emit a loud warning.
    """
    if cli_url:
        os.environ["PATCHER_API_DATABASE_URL"] = cli_url
        get_settings.cache_clear()

    resolved = get_settings().database_url
    try:
        path = make_url(resolved).database
    except Exception:
        return resolved, False
    is_relative_fallback = not path or not os.path.isabs(path)
    return resolved, is_relative_fallback


def _compute_expires_at(expires_in_days: int | None, no_expiry: bool) -> datetime | None:
    if no_expiry:
        return None
    days = expires_in_days if expires_in_days is not None else DEFAULT_LIFETIME.days
    return datetime.now(UTC) + timedelta(days=days)


async def grant_deploy_token(user_id: str, expires_at: datetime | None) -> str:
    await init_db()
    plaintext = secrets.token_urlsafe(32)
    async with get_session_maker()() as session:
        session.add(
            DeployToken(
                user_id=user_id,
                token_hash=hash_token(plaintext),
                expires_at=expires_at,
            )
        )
        await session.commit()
    return plaintext


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mint a deploy token for the /admin/catalog/upload endpoint.",
    )
    parser.add_argument(
        "user_id",
        help="Identifier for the token consumer (e.g. 'github-actions-runner').",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "Explicit SQLAlchemy URL for the target database. Overrides "
            "PATCHER_API_DATABASE_URL. Required on production hosts to avoid "
            "writing the token to a relative-path fallback file."
        ),
    )
    expiry = parser.add_mutually_exclusive_group()
    expiry.add_argument(
        "--expires-in-days",
        type=int,
        default=None,
        metavar="N",
        help=f"Token lifetime in days. Defaults to {DEFAULT_LIFETIME.days}.",
    )
    expiry.add_argument(
        "--no-expiry",
        action="store_true",
        help="Mint a token with no expiry. Use sparingly.",
    )
    args = parser.parse_args()

    database_url, is_relative_fallback = _resolve_database_url(args.database_url)

    if is_relative_fallback:
        print(
            "⚠ WARNING: resolved DB URL is a relative path. No value from the CLI",
            file=sys.stderr,
        )
        print(
            "  flag, shell env, /etc/patcher-api/env, or local .env was found.",
            file=sys.stderr,
        )
        print(f"  Resolved target: {database_url}", file=sys.stderr)
        print(
            "  The systemd service reads from a DIFFERENT file. Tokens minted here",
            file=sys.stderr,
        )
        print("  will NOT authenticate against the live API.", file=sys.stderr)
        print(
            "  Fix: pass --database-url, set PATCHER_API_DATABASE_URL, or run as a",
            file=sys.stderr,
        )
        print(
            "  user that can read /etc/patcher-api/env (typically `sudo -u patcher`).",
            file=sys.stderr,
        )
        print(file=sys.stderr)

    expires_at = _compute_expires_at(args.expires_in_days, args.no_expiry)
    plaintext = asyncio.run(grant_deploy_token(args.user_id, expires_at))

    print()
    print(f"Deploy token granted for '{args.user_id}':")
    print(f"  {plaintext}")
    print()
    if expires_at:
        print(f"Expires: {expires_at.isoformat()}")
    else:
        print("Expires: never")
    print(f"Database: {database_url}")
    print()
    print("Store this securely (GitHub Actions secret, 1Password, etc.)")
    print("It will not be shown again.")


if __name__ == "__main__":
    main()
