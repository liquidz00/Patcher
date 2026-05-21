"""
Fetch the AutoPkg recipe index and upsert each entry into the local DB.

Usage::

    cd api && uv run python scripts/ingest_autopkg.py

Safe to re-run. Existing records are updated, not duplicated. The upstream
index has ~15,000 recipes; a fresh sweep takes about a minute, most of
which is the single ~10MB JSON download.
"""

import asyncio
import sys

from patcher_api.db import get_session_maker, init_db
from patcher_api.ingest.autopkg import fetch_autopkg_index, ingest_autopkg_index


async def main() -> None:
    await init_db()

    print("Fetching AutoPkg recipe index...", file=sys.stderr)
    index_payload = await fetch_autopkg_index()
    identifiers = index_payload.get("identifiers", {})
    print(f"Got {len(identifiers)} recipes. Ingesting...", file=sys.stderr)

    async with get_session_maker()() as session:
        ingested, skipped = await ingest_autopkg_index(session, index_payload)

    print(f"Ingested {ingested} recipes, skipped {skipped}.", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
