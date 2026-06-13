"""
Async SQLAlchemy engine, session factory, and FastAPI session dependency.

Engine and session-maker are lazily constructed (and cached) so test code can
swap :func:`get_settings` before they're instantiated. Production code touches
nothing more than :func:`get_session` via FastAPI's ``Depends``.
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import lru_cache

from sqlalchemy import event
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from patcher_api.config import get_settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base all ORM models inherit from."""

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
        # WAL (and the pragmas below) are no-ops on the :memory: DB tests use; production picks them up.
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


def upsert_stmt(model, *, index_elements: list[str], **values):
    """
    Build an INSERT ... ON CONFLICT DO UPDATE whose update columns are derived
    from the inserted values (minus the conflict keys), so the insert and update
    paths can never desync.
    """
    stmt = sqlite_insert(model).values(**values)
    return stmt.on_conflict_do_update(
        index_elements=index_elements,
        set_={col: getattr(stmt.excluded, col) for col in values if col not in index_elements},
    )


async def run_in_savepoint(
    session: AsyncSession, work: Callable[[], Awaitable[object]], *, label: str
) -> bool:
    """
    Run one record's writes inside a SAVEPOINT so a single failure rolls back
    just that record, not the whole batch (the caller commits once at the end).

    The single per-record resilience primitive shared by the ingest and stitch
    loops. Returns ``True`` on success. On a database error it rolls the
    savepoint back, logs it with a traceback, and returns ``False`` so the loop
    can count it and move on. Anything that isn't a :class:`SQLAlchemyError`
    propagates — a real bug surfaces loudly instead of being silently tallied as
    a failed record.

    :param session: Async session with an active (auto-begun) transaction.
    :param work: Zero-arg callable returning the awaitable that does the writes.
    :param label: Human-readable record identifier for the failure log.
    """
    try:
        async with session.begin_nested():
            await work()
        return True
    except SQLAlchemyError:
        log.warning("Skipping %s: database error during write", label, exc_info=True)
        return False


async def execute_in_savepoint(session: AsyncSession, stmt, *, label: str) -> bool:
    """Run a single statement through :func:`run_in_savepoint`."""
    return await run_in_savepoint(session, lambda: session.execute(stmt), label=label)
