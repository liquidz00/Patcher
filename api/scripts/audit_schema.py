"""
Audit the live database schema against the ORM models.

Reflects the configured database and diffs it against ``Base.metadata`` to catch
drift the migration chain cannot see: a table or column that exists in the live
database but not in the models (an orphan, like the ``apps.cves`` NOT-NULL column
that silently froze the catalog), or one the models expect that the database
lacks.

The migration parity test (``tests/test_migrations.py``) compares the models to
the migration chain — both are "current," so they always agree. This compares
the *live* database, the only place historical drift can hide. Exits non-zero
when drift is found so a systemd unit or CI step can alert on it.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "api"))

import patcher_api.models  # noqa: F401  (registers every model on Base.metadata)
from patcher_api.config import get_settings
from patcher_api.db import Base
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine.url import make_url

# Alembic's own bookkeeping table is never modeled; it isn't drift.
_IGNORED_TABLES = {"alembic_version"}


def _sync_url(database_url: str) -> str:
    """Drop the async driver (``sqlite+aiosqlite`` -> ``sqlite``) so a sync engine can reflect."""
    url = make_url(database_url)
    return url.set(drivername=url.get_backend_name()).render_as_string(hide_password=False)


def find_drift(database_url: str) -> list[str]:
    """
    Return human-readable drift findings comparing the live schema to the models.

    An empty list means the database matches ``Base.metadata`` exactly (tables
    and columns). Orphan columns that are ``NOT NULL`` with no default are
    flagged as dangerous, because that's the shape that breaks every insert.
    """
    engine = create_engine(_sync_url(database_url))
    try:
        inspector = inspect(engine)
        live_tables = set(inspector.get_table_names()) - _IGNORED_TABLES
        model_tables = set(Base.metadata.tables)

        findings: list[str] = []
        for table in sorted(live_tables - model_tables):
            findings.append(f"orphan table {table!r} (in the database, not in the models)")
        for table in sorted(model_tables - live_tables):
            findings.append(
                f"MISSING table {table!r} (the models expect it; the database lacks it)"
            )

        for table in sorted(live_tables & model_tables):
            live_cols = {c["name"]: c for c in inspector.get_columns(table)}
            model_cols = set(Base.metadata.tables[table].columns.keys())
            for col in sorted(set(live_cols) - model_cols):
                info = live_cols[col]
                if not info["nullable"] and info.get("default") is None:
                    findings.append(
                        f"DANGEROUS orphan column {table}.{col} "
                        "(NOT NULL with no default, so it breaks every insert)"
                    )
                else:
                    findings.append(
                        f"orphan column {table}.{col} (in the database, not in the models)"
                    )
            for col in sorted(model_cols - set(live_cols)):
                findings.append(
                    f"MISSING column {table}.{col} (the models expect it; the database lacks it)"
                )
        return findings
    finally:
        engine.dispose()


def main() -> int:
    """Audit the configured database; print findings and return a process exit code."""
    url = get_settings().database_url
    findings = find_drift(url)
    if not findings:
        print(f"Schema audit clean: live database matches the models ({_sync_url(url)}).")
        return 0
    print(f"Schema drift detected ({len(findings)}):", file=sys.stderr)
    for finding in findings:
        print(f"  - {finding}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
