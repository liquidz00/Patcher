"""
Look up Mac App Store metadata for the curated seed bundle IDs and upsert
the results into the local DB.

Usage::

    cd api && uv run python scripts/ingest_mas.py

The seed list lives in :data:`patcher_api.ingest.mas.MAS_SEED_BUNDLE_IDS`.
Apple's iTunes Lookup API is rate-limited (~20 req/min); a default sweep
serializes the calls with a small inter-request delay and completes in
roughly two minutes.

Safe to re-run. Existing records are updated, not duplicated.
"""

import asyncio
import sys

from patcher_api.db import get_session_maker, init_db
from patcher_api.ingest.mas import MAS_SEED_BUNDLE_IDS, fetch_mas_lookup, ingest_mas_apps


async def main() -> None:
    await init_db()

    print(
        f"Looking up {len(MAS_SEED_BUNDLE_IDS)} bundle IDs against the MAS lookup API...",
        file=sys.stderr,
    )
    raw_records = await fetch_mas_lookup(MAS_SEED_BUNDLE_IDS)
    print(f"Got {len(raw_records)} records. Ingesting...", file=sys.stderr)

    async with get_session_maker()() as session:
        ingested, skipped = await ingest_mas_apps(session, raw_records)

    print(f"Ingested {ingested} records, skipped {skipped}.", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
