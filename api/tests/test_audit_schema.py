"""
Tests for the live-schema drift audit (``scripts/audit_schema.py``).

The audit reflects a database and diffs it against the ORM models, catching the
drift the migration parity guard can't see: a table or column present in the live
DB but not in the models (or vice versa). These build a temp DB via the migration
chain, introduce drift, and assert the audit reports it.
"""

import sqlite3
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from patcher_api.config import get_settings

_API_DIR = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _API_DIR / "alembic.ini"
sys.path.insert(0, str(_API_DIR / "scripts"))

from audit_schema import find_drift  # noqa: E402


def _build_db(tmp_path, monkeypatch, target: str = "head") -> str:
    """Build a temp DB at ``target`` revision and return its URL."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'live.db'}"
    monkeypatch.setenv("PATCHER_API_DATABASE_URL", url)
    get_settings.cache_clear()
    command.upgrade(Config(str(_ALEMBIC_INI)), target)
    get_settings.cache_clear()
    return url


def test_audit_clean_on_migrated_db(tmp_path, monkeypatch):
    """A DB migrated to head matches the models exactly: no findings."""
    assert find_drift(_build_db(tmp_path, monkeypatch)) == []


def test_audit_detects_orphan_table_and_column(tmp_path, monkeypatch):
    """An extra table and an extra column (the cves-style orphan) are both reported."""
    url = _build_db(tmp_path, monkeypatch)
    raw = sqlite3.connect(str(tmp_path / "live.db"))
    raw.execute("ALTER TABLE apps ADD COLUMN cves JSON NOT NULL DEFAULT '[]'")
    raw.execute("CREATE TABLE deploy_tokens (id INTEGER PRIMARY KEY, token TEXT)")
    raw.commit()
    raw.close()

    findings = find_drift(url)
    assert any("deploy_tokens" in f for f in findings)
    assert any("apps.cves" in f for f in findings)


def test_audit_detects_missing_column(tmp_path, monkeypatch):
    """A column the models expect but the DB lacks (here, pre-0002 schema) is reported MISSING."""
    url = _build_db(tmp_path, monkeypatch, target="0001")  # before apps.expected_team_id (0002)
    findings = find_drift(url)
    assert any("MISSING column apps.expected_team_id" in f for f in findings)
