"""
Stitch the catalog. Builds unified ``apps`` rows from already-ingested
Installomator labels, Homebrew Cask records, Mac App Store metadata, and
AutoPkg recipe-index entries.

Run AFTER the ingest scripts have populated their tables::

    cd api && uv run python scripts/ingest_installomator.py
    cd api && uv run python scripts/ingest_homebrew.py
    cd api && uv run python scripts/ingest_mas.py
    cd api && uv run python scripts/ingest_autopkg.py
    cd api && uv run python scripts/stitch_catalog.py

Safe to re-run. Existing ``apps`` rows are updated, not duplicated.
"""

import asyncio
import sys

from patcher_api.db import get_session_maker, init_db
from patcher_api.stitch import stitch_catalog


async def main() -> None:
    await init_db()

    print(
        "Stitching catalog from Installomator + Homebrew Cask + MAS + AutoPkg...",
        file=sys.stderr,
    )

    async with get_session_maker()() as session:
        (
            installomator_count,
            cask_only_count,
            both_sources,
            mas_only_count,
            autopkg_attached_count,
            failed,
        ) = await stitch_catalog(session)

    total = installomator_count + cask_only_count + mas_only_count
    print(
        f"Stitch complete.\n"
        f"  Installomator-sourced apps: {installomator_count}"
        f" (of which {both_sources} also matched a Homebrew Cask record)\n"
        f"  Cask-only apps:             {cask_only_count}\n"
        f"  MAS-only apps:              {mas_only_count}\n"
        f"  Apps with AutoPkg recipes:  {autopkg_attached_count}\n"
        f"  Total catalog rows:         {total}\n"
        f"  Failed:                     {failed} (see warnings above for details)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    asyncio.run(main())
