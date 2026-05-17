"""
Runtime configuration for the Patcher API.

Reads from environment variables prefixed with ``PATCHER_API_`` (also accepts a
``.env`` file alongside the working directory). Defaults are tuned for local
development against a SQLite file.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PATCHER_API_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./patcher_api.db"
    seed_on_startup: bool = True

    # Catalog-upload endpoint configuration. The endpoint streams the
    # uploaded DB to ``{incoming_dir}/patcher_api.db.tmp`` then atomically
    # renames to ``{incoming_dir}/patcher_api.db``. A systemd.path unit
    # watches that final filename and triggers the swap script.
    incoming_dir: Path = Path("/var/lib/patcher-api/incoming")
    # Cap protects against accidental or malicious oversized uploads. The
    # real catalog DB is ~80 MB uncompressed; 100 MB gives headroom.
    max_upload_bytes: int = 100 * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
