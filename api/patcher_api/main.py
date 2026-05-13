from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from patcher_api.config import get_settings
from patcher_api.db import get_engine, get_session_maker, init_db
from patcher_api.routes import apps
from patcher_api.seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()

    if get_settings().seed_on_startup:
        async with get_session_maker()() as session:
            await seed_database(session)

    yield

    await get_engine().dispose()


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
