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
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Path to the production env file
# Override via ``PATCHER_API_ENV_FILE`` to point at a different location
_ENV_FILE_PATH = os.environ.get("PATCHER_API_ENV_FILE", "/etc/patcher-api/env")


class Settings(BaseSettings):
    """API runtime settings, read from ``PATCHER_API_``-prefixed env vars and env files."""

    model_config = SettingsConfigDict(
        env_prefix="PATCHER_API_",
        env_file=(_ENV_FILE_PATH, ".env"),
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./patcher_api.db"
    seed_on_startup: bool = True
    admin_token: str = ""
    deploy_sentinel_path: str = ""
    # Jamf App Installers titles API. Override per-host if a real tenant is ever preferred.
    jai_base_url: str = "https://dummy.jamfcloud.com"
    jai_client_id: str = "2b7ea5e9-cbab-4f60-97e3-32eaefeee768"
    jai_client_secret: str = "o0dwi8E0XMaYtX760LB05csjHeJoGHKldTi4R5x7NKwLMl25gYenpMAlRDerA6G1"
    # MCP spec (2025-06-18) security MUST on Origin validation
    mcp_allowed_origins: list[str] = ["https://claude.ai"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
