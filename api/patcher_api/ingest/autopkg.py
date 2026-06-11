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
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.db import upsert_stmt
from patcher_api.models.autopkg import AutopkgRecipe
from patcher_api.schemas.autopkg import AutopkgIndexEntry

AUTOPKG_INDEX_URL = "https://raw.githubusercontent.com/autopkg/index/main/index.json"

# Cap on skip exemplars logged at DEBUG; aggregate counts instead of flooding per malformed row.
_MAX_SKIP_EXAMPLES_PER_REASON = 3

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

    # Aggregate skip reasons, logged once at the end (the upstream index has ~1000 malformed rows).
    skip_reason_counts: Counter[str] = Counter()
    skip_examples: dict[str, list[str]] = {}

    def _record_skip(reason: str, identifier: str) -> None:
        skip_reason_counts[reason] += 1
        bucket = skip_examples.setdefault(reason, [])
        if len(bucket) < _MAX_SKIP_EXAMPLES_PER_REASON:
            bucket.append(identifier)

    for identifier, entry in identifiers.items():
        if not isinstance(entry, dict):
            _record_skip("non-dict entry", identifier)
            skipped += 1
            continue

        try:
            record = AutopkgIndexEntry.model_validate(entry)
        except ValidationError as exc:
            # Build a compact reason key from the failing field names so the
            # aggregate log groups "name missing" separately from "path missing".
            reason = "validation: " + ", ".join(
                str(err["loc"][0]) for err in exc.errors() if err.get("loc")
            )
            _record_skip(reason, identifier)
            skipped += 1
            continue

        now = datetime.now(UTC)
        stmt = upsert_stmt(
            AutopkgRecipe,
            index_elements=["identifier"],
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
        await session.execute(stmt)
        ingested += 1

    await session.commit()

    # Surface aggregate skip reasons once, a few exemplars each, so noise stays flat regardless of malformed count.
    for reason, count in skip_reason_counts.most_common():
        examples = ", ".join(skip_examples.get(reason, []))
        log.warning(
            "Skipped %d AutoPkg recipes (%s); examples: %s",
            count,
            reason,
            examples,
        )

    return ingested, skipped
