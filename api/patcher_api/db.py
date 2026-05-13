"""
Async SQLAlchemy engine, session factory, and FastAPI session dependency.

Engine and session-maker are lazily constructed (and cached) so test code can
swap :func:`get_settings` before they're instantiated. Production code touches
nothing more than :func:`get_session` via FastAPI's ``Depends``.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from patcher_api.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_engine():
    return create_async_engine(get_settings().database_url, echo=False)


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
    (``seed``, ``grant_token``, ``ingest_homebrew``) so they work regardless of
    DB state. Imports :mod:`patcher_api.models` to guarantee every ORM model
    is registered on ``Base.metadata`` before ``create_all`` runs.
    """
    import patcher_api.models  # noqa: F401 — side-effect: register tables on Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
