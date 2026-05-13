"""Shared test fixtures.

Each test gets a fresh in-memory SQLite database, seeded from
:mod:`patcher_api.data`. The ``client`` fixture is pre-authorized with a
freshly-minted bearer token so route tests don't need to deal with auth
plumbing; tests that specifically want to exercise auth-failure paths can use
``unauth_client`` instead.
"""

import secrets
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from patcher_api.auth import hash_token
from patcher_api.db import Base, get_session
from patcher_api.main import app as fastapi_app
from patcher_api.models.token import Token
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
async def valid_token(test_session: AsyncSession) -> str:
    """Mint a fresh bearer token in the test DB and return the plaintext."""
    plaintext = secrets.token_urlsafe(32)
    test_session.add(Token(user_id="test-user", token_hash=hash_token(plaintext)))
    await test_session.commit()
    return plaintext


@pytest_asyncio.fixture
async def unauth_client(test_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Client with no Authorization header. Used for auth-failure tests."""

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield test_session

    fastapi_app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(unauth_client: AsyncClient, valid_token: str) -> AsyncClient:
    """Authorized client preloaded with a valid bearer token."""
    unauth_client.headers["Authorization"] = f"Bearer {valid_token}"
    return unauth_client
