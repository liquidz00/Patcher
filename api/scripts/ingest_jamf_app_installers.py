"""
Fetch the Jamf App Installers public HTML catalog, parse the title
table, and upsert each row into the local DB.

Usage::

    cd api && uv run python scripts/ingest_jamf_app_installers.py

Safe to re-run. Existing records are updated, not duplicated. Upstream
has ~345 titles in a single ~110KB HTML fetch; a sweep takes seconds.
"""

import asyncio
import sys

from patcher_api.db import get_session_maker, init_db
from patcher_api.ingest.jamf_app_installers import (
    fetch_jamf_app_installers_html,
    ingest_jamf_app_installers,
    parse_jamf_app_installers_table,
)


async def main() -> None:
    await init_db()

    print("Fetching Jamf App Installers catalog HTML...", file=sys.stderr)
    html = await fetch_jamf_app_installers_html()
    rows = parse_jamf_app_installers_table(html)
    print(f"Parsed {len(rows)} titles. Ingesting...", file=sys.stderr)

    async with get_session_maker()() as session:
        ingested, skipped = await ingest_jamf_app_installers(session, rows)

    print(f"Ingested {ingested} titles, skipped {skipped}.", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
