"""
Guard against test/prod schema-bootstrap divergence.

The suite builds each in-memory DB straight from the ORM models via
``Base.metadata.create_all`` (fast), while production builds the schema by
running the Alembic chain (``alembic upgrade head``). A migration that drifts
from the models — a forgotten column drop, a wrong type, a missing migration —
would never surface in the suite, because every other test gets the models'
schema directly. This runs both bootstrap paths and asserts they agree.
"""

from pathlib import Path

import patcher_api.models  # noqa: F401  (registers every model on Base.metadata)
from alembic import command
from alembic.config import Config
from patcher_api.config import get_settings
from patcher_api.db import Base
from sqlalchemy import create_engine, inspect

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _reflect_schema(engine) -> dict[str, dict[str, tuple[str, bool]]]:
    """Map each table (bar ``alembic_version``) to its columns' (type, nullable)."""
    inspector = inspect(engine)
    return {
        table: {
            col["name"]: (str(col["type"]), col["nullable"]) for col in inspector.get_columns(table)
        }
        for table in inspector.get_table_names()
        if table != "alembic_version"
    }


def test_migration_chain_matches_models(tmp_path, monkeypatch):
    """``alembic upgrade head`` must reproduce the schema the ORM models declare."""
    # Path 1 — the suite's bootstrap: create_all straight from the models.
    create_all_engine = create_engine(f"sqlite:///{tmp_path / 'create_all.db'}")
    Base.metadata.create_all(create_all_engine)
    expected = _reflect_schema(create_all_engine)
    create_all_engine.dispose()

    # Path 2 — production's bootstrap: run the migration chain to head. env.py
    # reads the URL from get_settings(), so redirect it at a throwaway file DB.
    migrated_path = tmp_path / "migrated.db"
    monkeypatch.setenv("PATCHER_API_DATABASE_URL", f"sqlite+aiosqlite:///{migrated_path}")
    get_settings.cache_clear()
    try:
        command.upgrade(Config(str(_ALEMBIC_INI)), "head")
    finally:
        get_settings.cache_clear()

    migrated_engine = create_engine(f"sqlite:///{migrated_path}")
    actual = _reflect_schema(migrated_engine)
    migrated_engine.dispose()

    assert actual == expected
