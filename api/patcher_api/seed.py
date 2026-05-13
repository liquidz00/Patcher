"""
Populate the database from the in-memory seed module.

Idempotent: if any apps already exist, the seed is skipped. This is what the
FastAPI lifespan calls on startup; it also works standalone via
``uv run python -m patcher_api.seed``.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.data import SEED_APPS, SEED_SOURCES
from patcher_api.db import get_session_maker, init_db
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow


async def seed_database(session: AsyncSession) -> int:
    """Insert seed records if the apps table is empty. Returns rows inserted."""
    existing = await session.scalar(select(AppRow).limit(1))
    if existing is not None:
        return 0

    for app in SEED_APPS:
        row = AppRow(
            bundle_id=app.bundle_id,
            name=app.name,
            vendor=app.vendor,
            current_version=app.current_version,
            latest_release_date=app.latest_release_date,
            download_url=str(app.download_url),
            install_method=app.install_method.value,
            sha256=app.sha256,
            sources=app.sources,
            cves=app.cves,
        )
        session.add(row)

    for bundle_id, sources in SEED_SOURCES.items():
        detail = AppSourceDetailRow(
            bundle_id=bundle_id,
            installomator=(
                sources.installomator.model_dump(mode="json") if sources.installomator else None
            ),
            homebrew_cask=(
                sources.homebrew_cask.model_dump(mode="json") if sources.homebrew_cask else None
            ),
            autopkg=(sources.autopkg.model_dump(mode="json") if sources.autopkg else None),
        )
        session.add(detail)

    await session.commit()
    return len(SEED_APPS)


async def _run_standalone() -> None:
    await init_db()
    async with get_session_maker()() as session:
        inserted = await seed_database(session)
        print(
            f"Seeded {inserted} app records." if inserted else "Database already seeded — skipping."
        )


if __name__ == "__main__":
    asyncio.run(_run_standalone())
