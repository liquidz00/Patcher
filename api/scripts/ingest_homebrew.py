"""
Fetch the Homebrew Cask catalog and upsert it into the local DB.

Usage::

    cd api && uv run python scripts/ingest_homebrew.py

Safe to re-run — existing records are updated, not duplicated.
"""

import asyncio
import sys

from patcher_api.db import get_session_maker, init_db
from patcher_api.ingest.homebrew import fetch_homebrew_casks, ingest_homebrew_casks


async def main() -> None:
    await init_db()

    print("Fetching Homebrew Cask catalog...", file=sys.stderr)
    raw_records = await fetch_homebrew_casks()
    print(f"Got {len(raw_records)} records. Ingesting...", file=sys.stderr)

    async with get_session_maker()() as session:
        ingested, skipped = await ingest_homebrew_casks(session, raw_records)

    print(f"Ingested {ingested} records, skipped {skipped}.", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
