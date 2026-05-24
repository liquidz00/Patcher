"""
Shared test fixtures.

Each test gets a fresh in-memory SQLite database, seeded from
:mod:`patcher_api.data`. The ``client`` fixture is an unauthenticated
AsyncClient suitable for the public ``/apps*`` and ``/health`` routes.
"""

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from patcher_api.db import Base, get_session
from patcher_api.main import app as fastapi_app
from patcher_api.seed import seed_database
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def test_engine() -> AsyncIterator:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine) -> AsyncIterator[AsyncSession]:
    session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_maker() as session:
        await seed_database(session)
        yield session


@pytest_asyncio.fixture
async def client(test_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Unauthenticated AsyncClient against the FastAPI app."""

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield test_session

    fastapi_app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()
