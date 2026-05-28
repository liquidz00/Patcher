"""
Catalog file hashing for the ``/apps*`` ETag.

The ETag is the SHA-256 of the on-disk SQLite catalog, computed once at
startup (the daily refresh restarts the service, so it stays current for the
process lifetime). Endpoints that mutate the catalog *without* a restart —
the macOS resolver upload — must call :func:`recompute_catalog_sha` after
writing, or revalidating clients keep getting ``304`` against a stale hash.

Lives in its own module so both :mod:`patcher_api.main` and the admin route
can use it without importing each other (``main`` imports the routers).
"""

import hashlib
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.engine.url import make_url

from patcher_api.config import get_settings

_HASH_CHUNK_BYTES = 65536


def catalog_db_path() -> Path | None:
    """
    On-disk path of the SQLite catalog, or ``None`` for in-memory databases.

    Tests run against ``sqlite+aiosqlite:///:memory:``; there's no file to
    hash, so callers treat ``None`` as "no ETag" and skip cache headers.
    """
    url = make_url(get_settings().database_url)
    if not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def hash_catalog_file(path: Path) -> str:
    """One-shot SHA-256 of the catalog DB file, ~1 second for a 65 MB DB."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_HASH_CHUNK_BYTES), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def recompute_catalog_sha(app: FastAPI) -> str | None:
    """
    Re-hash the catalog and store it on ``app.state.catalog_sha``.

    Returns the new hash, or ``None`` for an in-memory / missing DB (state is
    left untouched in that case). Called at startup and after any live write
    so the ``/apps*`` ETag reflects the current data instead of pinning to the
    hash captured when the process booted.
    """
    path = catalog_db_path()
    if path is None or not path.exists():
        return None
    sha = hash_catalog_file(path)
    app.state.catalog_sha = sha
    return sha
