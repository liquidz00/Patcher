"""
Fetch every Installomator label and upsert it into the local DB.

Usage::

    cd api && uv run python scripts/ingest_installomator.py

Pin a specific commit (recommended for reproducibility once we add drift
detection) by exporting the ref before invocation::

    export PATCHER_API_INSTALLOMATOR_REF=<sha>
    uv run python scripts/ingest_installomator.py

Safe to re-run — existing records are updated, not duplicated.
"""

import asyncio
import sys

from patcher_api.db import get_session_maker, init_db
from patcher_api.ingest.installomator import (
    fetch_installomator_labels,
    ingest_installomator_labels,
)


async def main() -> None:
    await init_db()

    print("Fetching Installomator Labels.txt + every fragment...", file=sys.stderr)
    name_to_content, missing, errored = await fetch_installomator_labels()
    print(
        f"Fetched {len(name_to_content)} fragments. "
        f"Missing (no fragment file, expected for ~170 alias/inline labels): {missing}. "
        f"Errored (network/5xx): {errored}.",
        file=sys.stderr,
    )

    async with get_session_maker()() as session:
        ingested, skipped, failed = await ingest_installomator_labels(session, name_to_content)

    print(
        f"Ingested {ingested} labels. "
        f"Skipped {skipped} (ignored team-IDs or empty parse). "
        f"Failed {failed} (unexpected errors during INSERT — see warnings above).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    asyncio.run(main())
