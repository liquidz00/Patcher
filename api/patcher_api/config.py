"""
Runtime configuration for the Patcher API.

Reads from environment variables prefixed with ``PATCHER_API_``.
Also reads from an env file at the path specified by ``PATCHER_API_ENV_FILE``
and from a ``.env`` alongside the working directory.
``os.environ`` overrides both files.

Defaults are tuned for local development against a SQLite file.

Precedence:
    1. ``PATCHER_API_ENV_FILE`` (defaults to ``/etc/patcher-api/env``).
       Operator scripts running as the `patcher` user inherit identical
       configuration without sourcing it in the shell.
    2. ``.env`` — local dev override alongside the working directory.
    3. Process environment (os.environ) — overrides everything above.

Catalog-upload configuration:
    The endpoint streams the uploaded DB to a temp location then atomically
    renames to ``{incoming_dir}/patcher_api.db``.
    A systemd.path unit watches that final filename and triggers the swap script.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Path to the production env file
# Override via ``PATCHER_API_ENV_FILE`` to point at a different location
_ENV_FILE_PATH = os.environ.get("PATCHER_API_ENV_FILE", "/etc/patcher-api/env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PATCHER_API_",
        # Missing files are silently skipped; the resolved settings still honor
        # the relative-path default if nothing else provides a value.
        env_file=(_ENV_FILE_PATH, ".env"),
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./patcher_api.db"
    seed_on_startup: bool = True
    incoming_dir: Path = Path("/var/lib/patcher-api/incoming")
    # Cap protects against accidental or malicious oversized uploads. The
    # real catalog DB is ~80 MB uncompressed; 100 MB gives headroom.
    max_upload_bytes: int = 100 * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
