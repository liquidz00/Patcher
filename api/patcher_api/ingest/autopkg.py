"""
AutoPkg recipe index ingestion.

Fetches the canonical recipe index from
``https://raw.githubusercontent.com/autopkg/index/main/index.json`` and
upserts each recipe entry into the ``autopkg_recipes`` table. Idempotent.
Records that fail Pydantic validation are logged and skipped; ingestion
continues for the rest of the batch.

The upstream index is rebuilt every ~4 hours by the autopkg/index repo's
GitHub Actions workflow. A single fetch returns ~15,000 recipes in one
JSON payload (~10MB). Single HTTP call per sweep; no rate-limit dance.

**Patcher catalogs recipes as a coverage indicator only**. We do not
execute recipes (AutoPkg itself is macOS-bound and the catalog is meant to
be source-agnostic). A recipe's presence answers "is there AutoPkg
automation available for this app and where does it live"; nothing more.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.models.autopkg import AutopkgRecipe
from patcher_api.schemas.autopkg import AutopkgIndexEntry

AUTOPKG_INDEX_URL = "https://raw.githubusercontent.com/autopkg/index/main/index.json"

log = logging.getLogger(__name__)


async def fetch_autopkg_index(
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """
    Fetch the upstream AutoPkg recipe index as raw JSON.

    Accepts an optional pre-configured ``httpx.AsyncClient`` so tests and
    callers that want custom timeouts/headers can inject one.

    :param client: Optional pre-configured ``httpx.AsyncClient``. If
        ``None``, a new client with a 60-second timeout is created and
        disposed of before returning.
    :type client: httpx.AsyncClient | None
    :return: The raw decoded JSON payload. Top-level shape is
        ``{"identifiers": {<identifier>: <entry>}, "shortnames": {...}}``.
    :rtype: dict[str, Any]
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=60.0)
    try:
        response = await client.get(AUTOPKG_INDEX_URL)
        response.raise_for_status()
        return response.json()
    finally:
        if owns_client:
            await client.aclose()


async def ingest_autopkg_index(
    session: AsyncSession,
    index_payload: dict[str, Any],
) -> tuple[int, int]:
    """
    Upsert AutoPkg recipe entries into the ``autopkg_recipes`` table.

    Walks the ``identifiers`` map. The ``shortnames`` map upstream is an
    inverted index (shortname → list of identifiers); we don't store it
    separately since it can be reconstructed from ``shortname`` columns
    on the recipe rows.

    :param session: Async SQLAlchemy session bound to the target DB.
    :type session: sqlalchemy.ext.asyncio.AsyncSession
    :param index_payload: Raw decoded ``index.json`` payload from
        :func:`fetch_autopkg_index`.
    :type index_payload: dict[str, Any]
    :return: ``(ingested, skipped)``. Ingested is the count of recipes
        upserted; skipped is the count that failed validation.
    :rtype: tuple[int, int]
    """
    ingested = skipped = 0
    identifiers = index_payload.get("identifiers", {})

    for identifier, entry in identifiers.items():
        if not isinstance(entry, dict):
            log.warning("Skipping non-dict AutoPkg entry for %r", identifier)
            skipped += 1
            continue

        try:
            record = AutopkgIndexEntry.model_validate(entry)
        except ValidationError as exc:
            log.warning("Skipping AutoPkg recipe %r: %s", identifier, exc)
            skipped += 1
            continue

        now = datetime.now(UTC)
        stmt = insert(AutopkgRecipe).values(
            identifier=identifier,
            name=record.name,
            shortname=record.shortname,
            repo=record.repo,
            path=record.path,
            parent_identifier=record.parent,
            inferred_type=record.inferred_type,
            description=record.description,
            raw=entry,
            ingested_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["identifier"],
            set_={
                "name": stmt.excluded.name,
                "shortname": stmt.excluded.shortname,
                "repo": stmt.excluded.repo,
                "path": stmt.excluded.path,
                "parent_identifier": stmt.excluded.parent_identifier,
                "inferred_type": stmt.excluded.inferred_type,
                "description": stmt.excluded.description,
                "raw": stmt.excluded.raw,
                "ingested_at": stmt.excluded.ingested_at,
            },
        )
        await session.execute(stmt)
        ingested += 1

    await session.commit()
    return ingested, skipped
