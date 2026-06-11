"""
Mac App Store metadata ingestion via Apple's iTunes Lookup API.

Looks up each seed ``bundle_id`` against ``itunes.apple.com/lookup`` and
upserts the resulting metadata into the ``mas_apps`` table. Idempotent.
Failed lookups (Apple returns ``resultCount: 0`` or HTTP errors) are
logged and skipped; the rest of the batch always reaches the end.

The "iTunes" name appears in this module and the Apple API URL only.
Everywhere else in the codebase (model name, table name, column on
``app_source_details``, schema names, route filter values, documentation)
we use **mas** because the iTunes brand has been retired for end users and
"Mac App Store" is the current, unambiguous name.

Apple's rate limit is approximately 20 requests per minute for the lookup
endpoint. The ingest serializes per-bundle calls and inserts a small
inter-request delay so a full seed sweep completes comfortably under that
ceiling. Sweeping the default seed list takes roughly two minutes; a much
larger seed would need to live behind a proper rate-limiter, but the
current scale doesn't justify the abstraction.
"""

import asyncio
import logging
from datetime import UTC, date, datetime
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.db import upsert_stmt
from patcher_api.models.mas import MasApp
from patcher_api.schemas.mas import MasLookupRecord

ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"

# Apple's lookup endpoint caps ~20 req/min; serialize + sleep to stay under without a token bucket.
_INTER_REQUEST_DELAY_SECONDS = 3.0

# Only "mac-software" results are real macOS apps; filter defensively (bundle_id collisions return iOS/TV/etc).
_MAS_KIND = "mac-software"

# Curated bundle IDs to sweep (Apple + popular paid apps); overlaps with Installomator/Cask gain "mas" as a source.
MAS_SEED_BUNDLE_IDS: list[str] = [
    # Apple iWork
    "com.apple.iWork.Pages",
    "com.apple.iWork.Numbers",
    "com.apple.iWork.Keynote",
    # Apple developer + pro media tools
    "com.apple.dt.Xcode",
    "com.apple.FinalCut",
    "com.apple.logic10",
    "com.apple.garageband10",
    "com.apple.iMovieApp",
    "com.apple.compressor",
    "com.apple.motionapp",
    "com.apple.mainstage",
    # Popular paid third-party MAS apps
    "com.pixelmatorteam.pixelmator.x",
    "com.culturedcode.ThingsMac",
    "com.flexibits.fantastical2.mac",
    "com.tableplus.TablePlus",
    # Microsoft Office (also distributed via Microsoft installers; the join
    # by bundle_id should add "mas" as an additional source dimension)
    "com.microsoft.Word",
    "com.microsoft.Excel",
    "com.microsoft.Powerpoint",
    "com.microsoft.Outlook",
    "com.microsoft.onenote.mac",
]

log = logging.getLogger(__name__)


def _parse_release_date(value: str | None) -> date | None:
    """
    Parse Apple's ISO 8601 release date into a ``date``. Returns ``None``
    on any parse failure rather than raising; release_date is informational
    and shouldn't poison ingestion when Apple sends something unexpected.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


async def fetch_mas_lookup(
    bundle_ids: list[str],
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """
    Look up each bundle_id against Apple's iTunes Lookup API.

    One HTTP call per bundle_id (Apple's lookup endpoint accepts comma-
    separated ``id`` values for iTunes IDs but not for ``bundleId``).
    Serialized with a small inter-request delay to stay under Apple's
    rate limit.

    :param bundle_ids: Bundle identifiers to look up.
    :type bundle_ids: list[str]
    :param client: Optional pre-configured ``httpx.AsyncClient``. If
        ``None``, a new client with a 30-second timeout is created and
        disposed of before returning.
    :type client: httpx.AsyncClient | None
    :return: List of raw result dicts as returned by Apple. Bundle IDs
        with no match are silently omitted.
    :rtype: list[dict[str, Any]]
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30.0)
    results: list[dict[str, Any]] = []
    try:
        for i, bundle_id in enumerate(bundle_ids):
            if i > 0:
                await asyncio.sleep(_INTER_REQUEST_DELAY_SECONDS)
            try:
                response = await client.get(ITUNES_LOOKUP_URL, params={"bundleId": bundle_id})
                response.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("Lookup failed for %r: %s", bundle_id, exc)
                continue

            payload = response.json()
            if payload.get("resultCount", 0) == 0:
                log.info("No MAS result for bundle_id=%r", bundle_id)
                continue
            results.extend(payload.get("results", []))
    finally:
        if owns_client:
            await client.aclose()
    return results


async def ingest_mas_apps(
    session: AsyncSession,
    raw_records: list[dict[str, Any]],
) -> tuple[int, int]:
    """
    Upsert MAS lookup results into the ``mas_apps`` table.

    Records that fail Pydantic validation, or whose ``kind`` field is not
    ``mac-software``, are logged and skipped; ingestion continues for the
    rest of the batch. We never block the whole sweep over one weird
    upstream record.

    :param session: Async SQLAlchemy session bound to the target DB.
    :type session: sqlalchemy.ext.asyncio.AsyncSession
    :param raw_records: List of raw lookup result dicts from
        :func:`fetch_mas_lookup`.
    :type raw_records: list[dict[str, Any]]
    :return: ``(ingested, skipped)``. Ingested is the count of records
        upserted; skipped is the count that failed validation or were
        non-Mac results.
    :rtype: tuple[int, int]
    """
    ingested = skipped = 0

    for raw in raw_records:
        try:
            record = MasLookupRecord.model_validate(raw)
        except ValidationError as exc:
            log.warning("Skipping MAS record %r: %s", raw.get("bundleId"), exc)
            skipped += 1
            continue

        if record.kind is not None and record.kind != _MAS_KIND:
            log.info(
                "Skipping non-Mac MAS result bundle_id=%r kind=%r",
                record.bundleId,
                record.kind,
            )
            skipped += 1
            continue

        now = datetime.now(UTC)
        stmt = upsert_stmt(
            MasApp,
            index_elements=["bundle_id"],
            bundle_id=record.bundleId,
            name=record.trackName,
            version=record.version,
            release_date=_parse_release_date(record.releaseDate),
            release_notes=record.releaseNotes,
            store_url=record.trackViewUrl,
            minimum_os_version=record.minimumOsVersion,
            price=record.price,
            raw=raw,
            ingested_at=now,
        )
        await session.execute(stmt)
        ingested += 1

    await session.commit()
    return ingested, skipped
