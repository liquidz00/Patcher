"""
Installomator label ingestion.

Fetches the list of available label names from Installomator's ``Labels.txt``,
pulls each label's ``.sh`` fragment in parallel (capped by an asyncio
semaphore), parses the variable assignments, and upserts into the
``installomator_labels`` table.

The parser mirrors Patcher's :class:`patcher.core.installomator.InstallomatorClient`
behavior — handling literal ``key="value"`` assignments, shell expressions
``key=$(...)`` stored as raw strings, and bash arrays ``key=(...)``. Shell
expressions are intentionally **not** evaluated; we store them verbatim and
defer evaluation to a future ingestion v2 (see the project memory's
"ingestion pipeline" section for rationale).

The default Installomator ref is ``refs/heads/main``. Override via the
``PATCHER_API_INSTALLOMATOR_REF`` environment variable (or pass ``ref=`` to
:func:`fetch_installomator_labels`) to pin a specific commit SHA — useful
once we add drift detection.
"""

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from patcher.core.installomator import parse_fragment
from patcher_api.models.installomator import InstallomatorLabel

__all__ = [
    "IGNORED_TEAMS",
    "fetch_installomator_labels",
    "ingest_installomator_labels",
    "parse_fragment",
]

# Apple Developer Team IDs we skip on ingestion. Mirrors Patcher's existing
# IGNORED_TEAMS list so the two implementations agree on which labels are
# excluded from the catalog.
IGNORED_TEAMS: set[str] = {"Frydendal", "Media", "LL3KBL2M3A"}

_INSTALLOMATOR_RAW_BASE = "https://raw.githubusercontent.com/Installomator/Installomator"
_DEFAULT_REF = "refs/heads/main"

# Limit concurrent fragment fetches. GitHub's raw endpoint is generous but
# blasting 700 simultaneous requests is rude.
_FETCH_CONCURRENCY = 10

log = logging.getLogger(__name__)


def _scalar_for_column(value: Any) -> str | None:
    """
    Coerce a parsed-label value into a string for a scalar TEXT column.

    Some labels declare variables with bash array syntax (e.g.
    ``appNewVersion=(${version}.${build})``) which the parser returns as a
    Python list. For the projected columns (which are scalar TEXT), we surface
    the first element — the full structure is still preserved in the ``raw``
    JSON column, so callers needing the array can recover it from there.

    :param value: A value from the parsed-fragment dict (string, list, or None).
    :type value: Any
    :return: Scalar string representation, or ``None`` for empty input.
    :rtype: str | None
    """
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def _installomator_ref() -> str:
    return os.environ.get("PATCHER_API_INSTALLOMATOR_REF", _DEFAULT_REF)


def _labels_txt_url(ref: str | None = None) -> str:
    return f"{_INSTALLOMATOR_RAW_BASE}/{ref or _installomator_ref()}/Labels.txt"


def _fragment_url(name: str, ref: str | None = None) -> str:
    return f"{_INSTALLOMATOR_RAW_BASE}/{ref or _installomator_ref()}/fragments/labels/{name}.sh"


async def fetch_installomator_labels(
    ref: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, str], int, int]:
    """
    Fetch Labels.txt and every label's ``.sh`` fragment from Installomator.

    Fetches happen in parallel with a concurrency cap of
    :data:`_FETCH_CONCURRENCY` to avoid hammering GitHub.

    Labels.txt is a **superset** of what exists as fragment files — some
    entries are aliases or defined inline in the main ``Installomator.sh``
    case statement and have no corresponding fragment. Those 404s are
    expected and are counted toward ``missing``, not ``errored``. Only
    unexpected errors (network failures, 5xx, rate limits) are logged.

    :param ref: Git ref (branch, tag, or SHA). Defaults to
        ``$PATCHER_API_INSTALLOMATOR_REF`` or ``refs/heads/main``.
    :type ref: str | None
    :param client: Optional pre-configured ``httpx.AsyncClient``. If ``None``,
        a new client with a 60-second timeout is created and disposed.
    :type client: httpx.AsyncClient | None
    :return: ``(name_to_content, missing, errored)`` — ``name_to_content``
        maps label name → raw ``.sh`` fragment content for every successful
        fetch; ``missing`` is the count of labels with no fragment file
        (expected 404s); ``errored`` is the count of labels that failed with
        an unexpected error.
    :rtype: tuple[dict[str, str], int, int]
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=60.0)
    try:
        labels_txt = await client.get(_labels_txt_url(ref))
        labels_txt.raise_for_status()

        names = {
            line.strip().lower()
            for line in labels_txt.text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        }

        semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)
        missing = errored = 0
        name_to_content: dict[str, str] = {}

        async def fetch_one(name: str) -> tuple[str, str | None, str]:
            nonlocal missing, errored
            async with semaphore:
                try:
                    response = await client.get(_fragment_url(name, ref))
                    if response.status_code == 404:
                        return name, None, "missing"
                    response.raise_for_status()
                    return name, response.text, "ok"
                except httpx.HTTPError as exc:
                    log.warning("Unexpected error fetching label %r: %s", name, exc)
                    return name, None, "errored"

        results = await asyncio.gather(*(fetch_one(name) for name in names))
        for name, content, status in results:
            if status == "ok" and content is not None:
                name_to_content[name] = content
            elif status == "missing":
                missing += 1
            else:
                errored += 1

        return name_to_content, missing, errored
    finally:
        if owns_client:
            await client.aclose()


async def ingest_installomator_labels(
    session: AsyncSession,
    name_to_content: dict[str, str],
) -> tuple[int, int, int]:
    """
    Parse the fetched fragments and upsert into the ``installomator_labels`` table.

    Each row is committed independently so a single problematic label can't
    roll back the whole batch. Failures are logged + counted toward
    ``failed``; the run always reaches the end.

    Labels whose ``expectedTeamID`` is in :data:`IGNORED_TEAMS` are skipped
    (counted toward ``skipped``). Empty parse results (fragments that yielded
    no recognizable variable assignments) are also skipped.

    :param session: Async SQLAlchemy session bound to the target DB.
    :type session: sqlalchemy.ext.asyncio.AsyncSession
    :param name_to_content: Dict mapping label name → raw ``.sh`` fragment
        content (typically returned by :func:`fetch_installomator_labels`).
    :type name_to_content: dict[str, str]
    :return: ``(ingested, skipped, failed)`` — ingested is the count of
        labels successfully stored; skipped is the count filtered out by
        team-ID exclusion or empty parse; failed is the count that raised
        an unexpected exception during INSERT.
    :rtype: tuple[int, int, int]
    """
    ingested = skipped = failed = 0

    for name, content in name_to_content.items():
        parsed = parse_fragment(content)
        if not parsed:
            skipped += 1
            continue

        if parsed.get("expectedTeamID") in IGNORED_TEAMS:
            skipped += 1
            continue

        try:
            now = datetime.now(UTC)
            stmt = insert(InstallomatorLabel).values(
                name=name,
                display_name=_scalar_for_column(parsed.get("name")),
                install_type=_scalar_for_column(parsed.get("type")),
                package_id=_scalar_for_column(parsed.get("packageID")),
                download_url=_scalar_for_column(parsed.get("downloadURL")),
                expected_team_id=_scalar_for_column(parsed.get("expectedTeamID")),
                app_new_version=_scalar_for_column(parsed.get("appNewVersion")),
                raw=parsed,
                ingested_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["name"],
                set_={
                    "display_name": stmt.excluded.display_name,
                    "install_type": stmt.excluded.install_type,
                    "package_id": stmt.excluded.package_id,
                    "download_url": stmt.excluded.download_url,
                    "expected_team_id": stmt.excluded.expected_team_id,
                    "app_new_version": stmt.excluded.app_new_version,
                    "raw": stmt.excluded.raw,
                    "ingested_at": stmt.excluded.ingested_at,
                },
            )
            await session.execute(stmt)
            await session.commit()
            ingested += 1
        except Exception as exc:
            await session.rollback()
            log.warning("Failed to ingest label %r: %s", name, exc)
            failed += 1

    return ingested, skipped, failed
