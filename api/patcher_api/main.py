from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from patcher_api.config import get_settings
from patcher_api.db import Base, get_engine, get_session_maker
from patcher_api.routes import apps
from patcher_api.seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if get_settings().seed_on_startup:
        async with get_session_maker()() as session:
            await seed_database(session)

    yield

    await engine.dispose()


app = FastAPI(
    title="Patcher API",
    description="Community catalog of macOS app patching metadata.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(apps.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
