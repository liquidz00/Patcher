"""
Runtime configuration for the Patcher API.

Reads from environment variables prefixed with ``PATCHER_API_`` (also accepts a
``.env`` file alongside the working directory). Defaults are tuned for local
development against a SQLite file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PATCHER_API_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./patcher_api.db"
    seed_on_startup: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
