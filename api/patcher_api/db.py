"""
Async SQLAlchemy engine, session factory, and FastAPI session dependency.

Engine and session-maker are lazily constructed (and cached) so test code can
swap :func:`get_settings` before they're instantiated. Production code touches
nothing more than :func:`get_session` via FastAPI's ``Depends``.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from patcher_api.config import get_settings


class Base(DeclarativeBase):
    pass


def _apply_sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    """
    Set per-connection SQLite pragmas tuned for a read-mostly catalog API.

    WAL is the load-bearing one: concurrent reads no longer block each
    other or block writes, which matters during ingest / swap. The cache
    and mmap settings keep hot pages in memory after the first read, so a
    typical request never touches disk after warmup. ``synchronous=NORMAL``
    relaxes the fsync cadence (durable on power loss with WAL, just not on
    every commit). ``temp_store=MEMORY`` keeps sort/join scratch in RAM
    rather than spilling.

    Notable absence: ``query_only=ON``. The user-token grant scripts and
    the seed-on-startup path both write to the DB; flipping the
    connection-wide read-only flag would break them. The runtime API
    surface is read-only by route inspection, not by pragma enforcement.
    """
    cur = dbapi_conn.cursor()
    try:
        # WAL is not supported for :memory: databases (the pragma returns
        # "memory" silently). Tests use :memory: so the WAL line is a no-op
        # there; production picks it up. Same applies to the other pragmas.
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA cache_size=-65536")  # 64 MB per connection
        cur.execute("PRAGMA mmap_size=268435456")  # 256 MB memory-mapped reads
    finally:
        cur.close()


@lru_cache(maxsize=1)
def get_engine():
    engine = create_async_engine(get_settings().database_url, echo=False)
    # The "connect" event fires on every fresh DBAPI connection; the pragmas
    # only persist for that one connection so we need to set them every time.
    event.listen(engine.sync_engine, "connect", _apply_sqlite_pragmas)
    return engine


@lru_cache(maxsize=1)
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_maker()() as session:
        yield session


async def init_db() -> None:
    """
    Create any missing tables. Idempotent — safe to call multiple times.

    Called by the FastAPI lifespan on server startup, and by standalone scripts
    (``seed``, ``grant_deploy_token``, ``ingest_homebrew``) so they work
    regardless of DB state. Imports :mod:`patcher_api.models` to guarantee
    every ORM model is registered on ``Base.metadata`` before ``create_all``
    runs.
    """
    import patcher_api.models  # noqa: F401 — side-effect: register tables on Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
