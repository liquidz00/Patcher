"""
Stitch the catalog — build unified ``apps`` rows from already-ingested
Installomator labels and Homebrew Cask records.

Run AFTER both ingest scripts have populated their tables::

    cd api && uv run python scripts/ingest_installomator.py
    cd api && uv run python scripts/ingest_homebrew.py
    cd api && uv run python scripts/stitch_catalog.py

Safe to re-run — existing ``apps`` rows are updated, not duplicated.
"""

import asyncio
import sys

from patcher_api.db import get_session_maker, init_db
from patcher_api.stitch import stitch_catalog


async def main() -> None:
    await init_db()

    print("Stitching catalog from Installomator + Homebrew Cask...", file=sys.stderr)

    async with get_session_maker()() as session:
        installomator_count, cask_only_count, both_sources, failed = await stitch_catalog(session)

    total = installomator_count + cask_only_count
    print(
        f"Stitch complete.\n"
        f"  Installomator-sourced apps: {installomator_count}"
        f" (of which {both_sources} also matched a Homebrew Cask record)\n"
        f"  Cask-only apps:             {cask_only_count}\n"
        f"  Total catalog rows:         {total}\n"
        f"  Failed:                     {failed} (see warnings above for details)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    asyncio.run(main())
