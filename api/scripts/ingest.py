"""
Unified entry point for Patcher API catalog ingestion + stitching.

Replaces the per-source ``ingest_*.py`` scripts. Shared setup (logging,
schema init, DB session) lives here once instead of being duplicated
across six near-identical files.

Usage::

    uv run python scripts/ingest.py installomator
    uv run python scripts/ingest.py homebrew
    uv run python scripts/ingest.py autopkg
    uv run python scripts/ingest.py jai
    uv run python scripts/ingest.py stitch
    uv run python scripts/ingest.py all

The Mac App Store (MAS) source is intentionally absent from this entry
point. The ingest module (:mod:`patcher_api.ingest.mas`) and its
``mas_apps`` table remain in the codebase for potential future
re-enablement, but the empirical signal-to-noise ratio (15 records from
a 20-bundle-ID seed, no bundle_id overlap with Installomator, no
download URL) and the rate-limited sequential lookup making it the
slowest pipeline step led to dropping it from routine refreshes. Stitch's
MAS phase no-ops gracefully against an empty ``mas_apps`` table.

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
  via pyinstallomator. Defaults to off (safe for production hosts). For
  local runs prefer the ``--resolve`` flag, which can't be silently dropped
  the way an unexported shell variable is. systemd's ``EnvironmentFile``
  exports correctly, so the env var is the right toggle on the box.
- ``PATCHER_API_RESOLVE_CONCURRENCY`` — concurrent label resolves
  during Installomator ingest. Defaults to 25.
- ``PATCHER_API_GITHUB_TOKEN`` — authenticates the ``api.github.com`` calls
  (the SHA-gating tree-discovery call and ``downloadURLFromGit``) to the
  5000/hr limit instead of the 60/hr unauthenticated one. Strongly
  recommended: without it, discovery itself can 403 once the shared 60/hr
  IP budget is spent. ``versionFromGit`` uses the github.com redirect and
  needs no token.
- ``PATCHER_API_INSTALLOMATOR_REF`` — pin a specific Installomator
  commit / tag / branch. Defaults to ``refs/heads/main``.
"""

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Awaitable, Callable

from patcher_api.config import get_settings
from patcher_api.db import get_session_maker, init_db
from patcher_api.ingest.autopkg import fetch_autopkg_index, ingest_autopkg_index
from patcher_api.ingest.homebrew import fetch_homebrew_casks, ingest_homebrew_casks
from patcher_api.ingest.jamf_app_installers import fetch_jai_catalog, ingest_jai_titles
from patcher_api.installomator.ingest import (
    fetch_installomator_labels,
    ingest_installomator_labels,
    refresh_dynamic_resolutions,
    set_resolve_on_ingest,
)
from patcher_api.models.installomator import InstallomatorLabel
from patcher_api.stitch import stitch_catalog
from sqlalchemy import delete, select

log = logging.getLogger("ingest")


def _configure_logging(verbose: bool = False) -> None:
    """One-time logging setup. Subcommands inherit this config.

    Root stays at WARNING so third-party libraries (httpx, httpcore,
    urllib3, sqlalchemy, asyncio) don't drown our progress messages in
    per-request INFO chatter. Patcher's own loggers (``patcher_api.*``
    and the top-level ``ingest`` logger this script uses) are bumped to
    INFO by default and DEBUG when ``-v`` is passed; third-party libs
    follow one level behind so ``-v`` users still get useful network
    detail without flipping a separate switch.
    """
    own_level = logging.DEBUG if verbose else logging.INFO
    third_party_level = logging.INFO if verbose else logging.WARNING

    logging.basicConfig(
        level=third_party_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("patcher_api").setLevel(own_level)
    logging.getLogger("ingest").setLevel(own_level)


async def cmd_installomator(*, force: bool = False) -> None:
    await init_db()
    log.info("=== Installomator ingest ===")
    async with get_session_maker()() as session:
        existing_rows = (
            await session.execute(select(InstallomatorLabel.name, InstallomatorLabel.blob_sha))
        ).all()
        existing_blob_shas: dict[str, str | None] = {name: sha for name, sha in existing_rows}

        plan = await fetch_installomator_labels(
            existing_blob_shas=existing_blob_shas,
            force=force,
        )

        ingested, skipped, failed = await ingest_installomator_labels(
            session,
            plan.name_to_content,
            name_to_blob_sha=plan.name_to_blob_sha,
        )

        # Keep dynamic values fresh for SHA-unchanged labels (no-op when
        # resolution is disabled). Re-resolves from stored ``raw``.
        refreshed = await refresh_dynamic_resolutions(
            session, already_resolved=set(plan.name_to_content)
        )

        if plan.removed:
            log.info(
                "Deleting %d label(s) removed upstream: %s",
                len(plan.removed),
                ", ".join(sorted(plan.removed)),
            )
            await session.execute(
                delete(InstallomatorLabel).where(InstallomatorLabel.name.in_(plan.removed))
            )
            await session.commit()

    log.info(
        "Installomator summary: fetched=%d, unchanged=%d, removed=%d, "
        "missing=%d, errored=%d, ingested=%d, skipped=%d, failed=%d, refreshed=%d",
        len(plan.name_to_content),
        plan.unchanged,
        len(plan.removed),
        plan.missing,
        plan.errored,
        ingested,
        skipped,
        failed,
        refreshed,
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
    settings = get_settings()
    log.info("Fetching JAI titles catalog from %s...", settings.jai_base_url)
    titles = await fetch_jai_catalog(
        settings.jai_base_url, settings.jai_client_id, settings.jai_client_secret
    )
    log.info("Fetched %d titles. Ingesting...", len(titles))
    async with get_session_maker()() as session:
        ingested, skipped = await ingest_jai_titles(session, titles)
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


async def cmd_all(*, force: bool = False) -> None:
    log.info("=== Full pipeline ===")
    await cmd_installomator(force=force)
    await cmd_homebrew()
    await cmd_autopkg()
    await cmd_jai()
    await cmd_stitch()
    log.info("=== Full pipeline complete ===")


COMMANDS: dict[str, Callable[..., Awaitable[None]]] = {
    "installomator": cmd_installomator,
    "homebrew": cmd_homebrew,
    "autopkg": cmd_autopkg,
    "jai": cmd_jai,
    "stitch": cmd_stitch,
    "all": cmd_all,
}

# Commands that accept ``force=`` for SHA-gated re-ingest. Other commands
# either have no gating to bypass (stitch, JAI) or their upstream sources
# don't yet support SHA gating.
_FORCEABLE_COMMANDS = frozenset({"installomator", "all"})


def _env_force() -> bool:
    """Read ``PATCHER_API_FORCE_INGEST`` and coerce to bool."""
    return os.environ.get("PATCHER_API_FORCE_INGEST", "").lower() in ("1", "true", "yes")


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
        "--force",
        action="store_true",
        help=(
            "Bypass SHA gating on supported sources (installomator). "
            "Forces every label to be re-fetched and re-parsed regardless "
            "of stored blob_sha. Use after parser changes or when the "
            "resolver's coverage improves. Also honors PATCHER_API_FORCE_INGEST=1."
        ),
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help=(
            "Resolve shell-expression downloadURL / appNewVersion values during "
            "the installomator ingest, equivalent to PATCHER_API_RESOLVE_INGEST=true. "
            "Prefer this flag for local runs — it can't be silently dropped the way "
            "an unexported env var is. HTTP-bound; run on a machine with adequate RAM."
        ),
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

    if args.resolve:
        set_resolve_on_ingest(True)
        if args.command not in _FORCEABLE_COMMANDS:
            log.warning(
                "--resolve is a no-op for the '%s' command (only installomator + all resolve).",
                args.command,
            )

    force = args.force or _env_force()
    if force and args.command not in _FORCEABLE_COMMANDS:
        log.warning(
            "--force is a no-op for the '%s' command (only installomator + all support gating today).",
            args.command,
        )

    if args.command in _FORCEABLE_COMMANDS:
        coro = COMMANDS[args.command](force=force)
    else:
        coro = COMMANDS[args.command]()
    asyncio.run(coro)


if __name__ == "__main__":
    main()
