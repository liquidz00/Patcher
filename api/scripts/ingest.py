"""
Unified entry point for Patcher API catalog ingestion + stitching.

Replaces the per-source ``ingest_*.py`` scripts. Shared setup (logging,
schema init, DB session) lives here once instead of being duplicated
across six near-identical files.

Usage::

    uv run python scripts/ingest.py installomator
    uv run python scripts/ingest.py homebrew
    uv run python scripts/ingest.py mas
    uv run python scripts/ingest.py autopkg
    uv run python scripts/ingest.py jai
    uv run python scripts/ingest.py stitch
    uv run python scripts/ingest.py all

Each subcommand corresponds to a single upstream source (or the stitch
phase that joins them). ``all`` runs every ingest in sequence, then
stitches the catalog — matching what the daily refresh GitHub Actions
workflow does on a clean run.

The actual ingest logic lives in :mod:`patcher_api.ingest.*` and
:mod:`patcher_api.stitch`. This script is a thin orchestration layer:
configure logging once, init the schema, run the requested phase, log
the summary. Per-source progress logging lives inside the ingest module
functions themselves so it fires regardless of how they're invoked.

Environment variables:

- ``PATCHER_API_DATABASE_URL`` — target database (defaults to
  ``sqlite+aiosqlite:///./patcher_api.db``). Required on production
  hosts; the systemd service reads from a specific absolute path that
  the relative default will not resolve to.
- ``PATCHER_API_RESOLVE_INGEST`` — when set, the Installomator ingest
  evaluates shell-expression ``downloadURL`` / ``appNewVersion`` values
  via pyinstallomator. Defaults to off (safe for production hosts).
- ``PATCHER_API_RESOLVE_CONCURRENCY`` — concurrent label resolves
  during Installomator ingest. Defaults to 25.
- ``PATCHER_API_INSTALLOMATOR_REF`` — pin a specific Installomator
  commit / tag / branch. Defaults to ``refs/heads/main``.
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable

from patcher_api.db import get_session_maker, init_db
from patcher_api.ingest.autopkg import fetch_autopkg_index, ingest_autopkg_index
from patcher_api.ingest.homebrew import fetch_homebrew_casks, ingest_homebrew_casks
from patcher_api.ingest.installomator import (
    fetch_installomator_labels,
    ingest_installomator_labels,
)
from patcher_api.ingest.jamf_app_installers import (
    fetch_jamf_app_installers_html,
    ingest_jamf_app_installers,
    parse_jamf_app_installers_table,
)
from patcher_api.ingest.mas import MAS_SEED_BUNDLE_IDS, fetch_mas_lookup, ingest_mas_apps
from patcher_api.stitch import stitch_catalog

log = logging.getLogger("ingest")


def _configure_logging(verbose: bool = False) -> None:
    """One-time logging setup. Subcommands inherit this config."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


async def cmd_installomator() -> None:
    await init_db()
    log.info("=== Installomator ingest ===")
    name_to_content, missing, errored = await fetch_installomator_labels()
    async with get_session_maker()() as session:
        ingested, skipped, failed = await ingest_installomator_labels(session, name_to_content)
    log.info(
        "Installomator summary: fetched=%d, missing=%d, errored=%d, "
        "ingested=%d, skipped=%d, failed=%d",
        len(name_to_content),
        missing,
        errored,
        ingested,
        skipped,
        failed,
    )


async def cmd_homebrew() -> None:
    await init_db()
    log.info("=== Homebrew Cask ingest ===")
    log.info("Fetching Homebrew Cask catalog...")
    raw_records = await fetch_homebrew_casks()
    log.info("Fetched %d records. Ingesting...", len(raw_records))
    async with get_session_maker()() as session:
        ingested, skipped = await ingest_homebrew_casks(session, raw_records)
    log.info("Homebrew summary: ingested=%d, skipped=%d", ingested, skipped)


async def cmd_mas() -> None:
    await init_db()
    log.info("=== Mac App Store ingest ===")
    log.info(
        "Looking up %d seed bundle IDs (rate-limited to ~20 req/min)...",
        len(MAS_SEED_BUNDLE_IDS),
    )
    raw_records = await fetch_mas_lookup(MAS_SEED_BUNDLE_IDS)
    log.info("Fetched %d records. Ingesting...", len(raw_records))
    async with get_session_maker()() as session:
        ingested, skipped = await ingest_mas_apps(session, raw_records)
    log.info("MAS summary: ingested=%d, skipped=%d", ingested, skipped)


async def cmd_autopkg() -> None:
    await init_db()
    log.info("=== AutoPkg recipe index ingest ===")
    log.info("Fetching AutoPkg recipe index (~10MB)...")
    index_payload = await fetch_autopkg_index()
    identifiers = index_payload.get("identifiers", {})
    log.info("Got %d recipes. Ingesting...", len(identifiers))
    async with get_session_maker()() as session:
        ingested, skipped = await ingest_autopkg_index(session, index_payload)
    log.info("AutoPkg summary: ingested=%d, skipped=%d", ingested, skipped)


async def cmd_jai() -> None:
    await init_db()
    log.info("=== Jamf App Installers ingest ===")
    log.info("Fetching JAI catalog HTML...")
    html = await fetch_jamf_app_installers_html()
    rows = parse_jamf_app_installers_table(html)
    log.info("Parsed %d titles. Ingesting...", len(rows))
    async with get_session_maker()() as session:
        ingested, skipped = await ingest_jamf_app_installers(session, rows)
    log.info("JAI summary: ingested=%d, skipped=%d", ingested, skipped)


async def cmd_stitch() -> None:
    await init_db()
    log.info("=== Stitch catalog ===")
    log.info("Joining Installomator + Cask + MAS + AutoPkg + JAI into unified apps rows...")
    async with get_session_maker()() as session:
        (
            installomator_count,
            cask_only_count,
            both_sources,
            mas_only_count,
            mas_merged_count,
            autopkg_attached_count,
            jai_attached_count,
            failed,
        ) = await stitch_catalog(session)
    total = installomator_count + cask_only_count + mas_only_count
    log.info(
        "Stitch summary: installomator=%d (cask_overlap=%d), cask_only=%d, "
        "mas_only=%d, mas_merged=%d, autopkg_attached=%d, jai_attached=%d, "
        "total=%d, failed=%d",
        installomator_count,
        both_sources,
        cask_only_count,
        mas_only_count,
        mas_merged_count,
        autopkg_attached_count,
        jai_attached_count,
        total,
        failed,
    )


async def cmd_all() -> None:
    log.info("=== Full pipeline ===")
    await cmd_installomator()
    await cmd_homebrew()
    await cmd_mas()
    await cmd_autopkg()
    await cmd_jai()
    await cmd_stitch()
    log.info("=== Full pipeline complete ===")


COMMANDS: dict[str, Callable[[], Awaitable[None]]] = {
    "installomator": cmd_installomator,
    "homebrew": cmd_homebrew,
    "mas": cmd_mas,
    "autopkg": cmd_autopkg,
    "jai": cmd_jai,
    "stitch": cmd_stitch,
    "all": cmd_all,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Patcher API catalog ingestion + stitching.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    parser.add_argument(
        "command",
        choices=list(COMMANDS.keys()),
        help=(
            "Which source to ingest, or 'all' to run the full pipeline followed "
            "by stitch. 'stitch' runs the join phase on already-ingested data."
        ),
    )
    args = parser.parse_args()
    _configure_logging(verbose=args.verbose)
    asyncio.run(COMMANDS[args.command]())


if __name__ == "__main__":
    main()
