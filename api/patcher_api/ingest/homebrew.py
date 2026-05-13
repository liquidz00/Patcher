"""
Homebrew Cask ingestion.

Pulls the complete Cask catalog (~7k records) from
``https://formulae.brew.sh/api/cask.json`` and upserts each into the
``homebrew_casks`` table. Idempotent — subsequent runs update existing rows
rather than failing or duplicating.

Records that fail Pydantic validation are logged and skipped; ingestion
continues for the rest of the batch. We never block the whole catalog over
one weird upstream record.
"""

import logging
from datetime import UTC, datetime

import httpx
from pydantic import ValidationError
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.models.homebrew import HomebrewCask
from patcher_api.schemas.homebrew import HomebrewCaskRecord

HOMEBREW_CASK_API_URL = "https://formulae.brew.sh/api/cask.json"

log = logging.getLogger(__name__)


async def fetch_homebrew_casks(client: httpx.AsyncClient | None = None) -> list[dict]:
    """
    Fetch the complete Homebrew Cask catalog as raw JSON.

    Accepts an optional pre-configured ``httpx.AsyncClient`` so tests and
    callers that want custom timeouts/headers can inject one.

    :param client: Optional pre-configured ``httpx.AsyncClient``. If ``None``,
        a new client with a 60-second timeout is created and disposed of
        before returning.
    :type client: httpx.AsyncClient | None
    :return: List of raw Cask records as dicts (the upstream JSON shape).
    :rtype: list[dict]
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=60.0)
    try:
        response = await client.get(HOMEBREW_CASK_API_URL)
        response.raise_for_status()
        return response.json()
    finally:
        if owns_client:
            await client.aclose()


async def ingest_homebrew_casks(
    session: AsyncSession,
    raw_records: list[dict],
) -> tuple[int, int]:
    """
    Upsert Cask records into the ``homebrew_casks`` table.

    :param session: Async SQLAlchemy session bound to the target DB.
    :type session: sqlalchemy.ext.asyncio.AsyncSession
    :param raw_records: List of raw Cask record dicts (the upstream JSON shape).
    :type raw_records: list[dict]
    :return: ``(ingested, skipped)`` — ingested is the count of records that
        parsed and were upserted; skipped is the count that failed Pydantic
        validation.
    :rtype: tuple[int, int]
    """
    ingested = skipped = 0

    for raw in raw_records:
        try:
            record = HomebrewCaskRecord.model_validate(raw)
        except ValidationError as exc:
            log.warning("Skipping cask %r: %s", raw.get("token"), exc)
            skipped += 1
            continue

        now = datetime.now(UTC)
        stmt = insert(HomebrewCask).values(
            token=record.token,
            name=record.name[0] if record.name else record.token,
            desc=record.desc,
            homepage=record.homepage,
            url=record.url,
            version=record.version,
            sha256=record.sha256,
            auto_updates=record.auto_updates,
            raw=raw,
            ingested_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["token"],
            set_={
                "name": stmt.excluded.name,
                "desc": stmt.excluded.desc,
                "homepage": stmt.excluded.homepage,
                "url": stmt.excluded.url,
                "version": stmt.excluded.version,
                "sha256": stmt.excluded.sha256,
                "auto_updates": stmt.excluded.auto_updates,
                "raw": stmt.excluded.raw,
                "ingested_at": stmt.excluded.ingested_at,
            },
        )
        await session.execute(stmt)
        ingested += 1

    await session.commit()
    return ingested, skipped
