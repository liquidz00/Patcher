"""
Installomator label ingestion.

Discovers labels by calling GitHub's git/trees API
(``GET /repos/Installomator/Installomator/git/trees/<ref>?recursive=1``)
once per run. The response carries every label fragment's blob SHA
alongside its path, which serves two purposes: it's the canonical list
of fragments that actually exist (no more ``Labels.txt`` alias 404 noise)
and it's a content-addressed identity per file. Pulls each fragment's
``.sh`` in parallel (capped by an asyncio semaphore), parses the variable
assignments, and upserts into the ``installomator_labels`` table.

**SHA gating:** stored ``blob_sha`` values are diffed against the upstream
tree before any fragment fetches. Labels whose SHA matches are skipped
entirely (no fragment fetch, no parse, no resolver call). The first
ingest after a fresh schema or a ``--force`` run re-fetches everything
because no prior SHA exists to compare against.

The parser mirrors Patcher's :class:`patcher.clients.installomator.InstallomatorClient`
behavior — handling literal ``key="value"`` assignments, shell expressions
``key=$(...)`` stored as raw strings, and bash arrays ``key=(...)``.

**Shell expression handling for ``downloadURL`` and ``appNewVersion``** is
controlled by the ``PATCHER_API_RESOLVE_INGEST`` env var:

- **Default (unset / false):** shell expressions land as ``NULL`` in the
  projected columns. The full raw value still lives in the ``raw`` JSON
  column. This is the safe default for production hosts; the resolver is
  HTTP-bound and OOMs on small instances during bulk ingest.
- **Set to ``true``/``1``/``yes``:** each shell expression is evaluated via
  :func:`patcher_api.installomator.resolver.resolve` (the "pyinstallomator" port).
  Resolved values land in the projected columns; unresolvable expressions
  still go to ``NULL``. Run on a workstation with adequate RAM — the
  resolver fans 1000+ HTTP requests across upstream vendor sites.

The default Installomator ref is ``refs/heads/main``. Override via the
``PATCHER_API_INSTALLOMATOR_REF`` environment variable (or pass ``ref=`` to
:func:`fetch_installomator_labels`) to pin a specific commit SHA — useful
once we add drift detection.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.installomator.parser import parse_fragment
from patcher_api.installomator.resolver import (
    InvalidOutput,
    Resolved,
    Unresolvable,
    is_shell_expression,
    resolve,
)
from patcher_api.models.installomator import InstallomatorLabel

__all__ = [
    "IGNORED_TEAMS",
    "FetchPlan",
    "fetch_installomator_labels",
    "ingest_installomator_labels",
    "parse_fragment",
]

# Mirror existing IGNORED_TEAMS list
IGNORED_TEAMS: set[str] = {"Frydendal", "Media", "LL3KBL2M3A"}

_INSTALLOMATOR_RAW_BASE = "https://raw.githubusercontent.com/Installomator/Installomator"
_GITHUB_API_BASE = "https://api.github.com"
_DEFAULT_REF = "refs/heads/main"

# Don't be rude, limit requests sent
_FETCH_CONCURRENCY = 10

# Limit concurrent resolve operations during ingest.
#   Each resolve can spawn a bash subprocess (for unsupported pipelines)
#   or hit upstream vendor sites, so this is a CPU + network-bound mix.
#
# Override via PATCHER_API_RESOLVE_CONCURRENCY for tuning on tighter hosts.
_RESOLVE_CONCURRENCY = int(os.environ.get("PATCHER_API_RESOLVE_CONCURRENCY", "25"))

# Progress interval for logging (every N titles gets a logging statement)
_PROGRESS_EVERY = 100

# Label Resolution (opt-in).
#   When set, shell-expression dynamic values are resolved instead of being nulled out.
_RESOLVE_ON_INGEST = os.environ.get("PATCHER_API_RESOLVE_INGEST", "").lower() in (
    "1",
    "true",
    "yes",
)

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


def _resolve_or_null(
    value: str | None,
    http_client: httpx.Client | None = None,
    *,
    is_url: bool = False,
) -> str | None:
    """
    Evaluate a label value via pyinstallomator's :func:`resolve`. Returns the
    final string when resolve produces :class:`Resolved`, otherwise ``None``
    when it produces :class:`Unresolvable` or :class:`InvalidOutput`.

    URL validation lives inside :func:`resolve` itself when ``is_url=True``:
    a value that fails :func:`looks_like_clean_http_url` comes back as
    :class:`InvalidOutput`, which this wrapper nulls. Callers don't have to
    re-apply the validator.

    Synchronous and HTTP-bound. Wrap in :func:`asyncio.to_thread` when calling
    from an async context to avoid blocking the event loop while pipelines
    fan out to upstream sites.

    :param value: Raw value from the parsed label fragment.
    :type value: str | None
    :param http_client: Pre-configured ``httpx.Client`` reused across calls.
        When ``None``, :func:`resolve` creates a fresh client per curl
        invocation. Fine for one-off use, but spawns thousands of clients
        (each with its own SSL context) during a full ingest, which OOMs
        small hosts. Callers running a batch should construct one client
        and pass it in.
    :type http_client: httpx.Client | None
    :param is_url: When ``True``, the resolved value is run through
        :func:`looks_like_clean_http_url` inside :func:`resolve` itself.
        Pass for fields whose projected column is later serialized as
        ``HttpUrl``. Defaults to ``False`` for non-URL fields
        (e.g. ``appNewVersion``).
    :type is_url: bool
    :return: Clean literal usable as a projected column value, or ``None``.
    :rtype: str | None
    """
    if value is None:
        return None
    if not _RESOLVE_ON_INGEST:
        # Resolution disabled. Null shell expressions without attempting any
        # HTTP-bound evaluation. Plain literals still flow through
        # :func:`resolve` so the URL validator runs on them (catches literal
        # ftp:// label values and similar).
        if is_shell_expression(value):
            return None
    outcome = resolve(value, http_client=http_client, is_url=is_url)
    match outcome:
        case Resolved(value=resolved_value):
            # Belt-and-suspenders: even literal pass-throughs can carry
            # embedded substitutions the anchored resolver didn't touch.
            if is_shell_expression(resolved_value):
                return None
            return resolved_value
        case Unresolvable() | InvalidOutput():
            return None


def _installomator_ref() -> str:
    return os.environ.get("PATCHER_API_INSTALLOMATOR_REF", _DEFAULT_REF)


def _tree_api_ref(ref: str | None = None) -> str:
    """
    Normalize a ref for GitHub's tree API.

    The raw-content URLs accept ``refs/heads/main``; the tree API expects
    a bare ref name (``main``, a tag, or a commit SHA). Strip the prefix.
    """
    return (ref or _installomator_ref()).removeprefix("refs/heads/")


def _tree_api_url(ref: str | None = None) -> str:
    return (
        f"{_GITHUB_API_BASE}/repos/Installomator/Installomator/git/trees/"
        f"{_tree_api_ref(ref)}?recursive=1"
    )


def _fragment_url(name: str, ref: str | None = None) -> str:
    return f"{_INSTALLOMATOR_RAW_BASE}/{ref or _installomator_ref()}/fragments/labels/{name}.sh"


async def _fetch_upstream_tree(
    ref: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, str]:
    """
    Fetch the upstream tree and return ``{label_name: blob_sha}``.

    One HTTP call returns every file in the repo with its content SHA;
    we filter to ``fragments/labels/*.sh`` blobs. The returned map is
    the authoritative discovery list — names exist iff a fragment file
    exists, so this replaces ``Labels.txt`` (which is a superset that
    includes inline aliases without fragments).

    :param ref: Git ref to query (branch, tag, or commit SHA). Defaults
        to ``$PATCHER_API_INSTALLOMATOR_REF`` or ``main``.
    :type ref: str | None
    :param client: Optional pre-configured ``httpx.AsyncClient``.
    :type client: httpx.AsyncClient | None
    :return: Mapping of label name (e.g. ``"firefoxpkg"``) to its
        upstream blob SHA.
    :rtype: dict[str, str]
    :raises httpx.HTTPError: On network failure or non-2xx tree response.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=60.0)
    try:
        response = await client.get(_tree_api_url(ref))
        response.raise_for_status()
        data = response.json()
        if data.get("truncated"):
            log.warning(
                "GitHub tree response was truncated; some labels may be missing. "
                "This is unexpected for the Installomator repo — investigate.",
            )
        upstream: dict[str, str] = {}
        for entry in data.get("tree", []):
            path = entry.get("path", "")
            if (
                entry.get("type") == "blob"
                and path.startswith("fragments/labels/")
                and path.endswith(".sh")
            ):
                name = path.removeprefix("fragments/labels/").removesuffix(".sh").lower()
                upstream[name] = entry["sha"]
        return upstream
    finally:
        if owns_client:
            await client.aclose()


@dataclass(frozen=True)
class FetchPlan:
    """
    Outcome of a gated label fetch.

    :ivar name_to_content: Raw ``.sh`` fragment text for every label that
        was actually fetched this run (i.e. SHA changed, new, or
        ``force=True``). Empty when nothing changed upstream.
    :ivar name_to_blob_sha: Full upstream view: every label name with its
        current blob SHA. Used by the ingest step to persist the SHA
        even for upserts of unchanged-but-re-fetched rows.
    :ivar removed: Labels that exist in the local DB but are absent from
        upstream — caller is expected to delete these.
    :ivar unchanged: Count of labels skipped because their SHA matched
        what's already stored. Zero on a fresh DB or a ``--force`` run.
    :ivar missing: Count of fragments that 404'd during fetch. Should be
        zero now that discovery is tree-driven (the tree only lists files
        that exist); kept for defensive logging if upstream removes a
        file mid-run.
    :ivar errored: Count of fragments that failed with an unexpected
        error during fetch.
    """

    name_to_content: dict[str, str] = field(default_factory=dict)
    name_to_blob_sha: dict[str, str] = field(default_factory=dict)
    removed: frozenset[str] = field(default_factory=frozenset)
    unchanged: int = 0
    missing: int = 0
    errored: int = 0


async def fetch_installomator_labels(
    ref: str | None = None,
    client: httpx.AsyncClient | None = None,
    *,
    existing_blob_shas: dict[str, str] | None = None,
    force: bool = False,
) -> FetchPlan:
    """
    Fetch the upstream tree, diff against ``existing_blob_shas``, and
    download fragments only for labels whose content changed.

    Tree-API discovery yields ``{name: blob_sha}`` for every label
    fragment that exists upstream. Three sets fall out of the diff:

    - **changed**: name in upstream and (``force`` or
      ``upstream[name] != existing.get(name)``). Fragment is fetched.
    - **unchanged**: name in upstream with matching SHA in
      ``existing_blob_shas``. Skipped entirely.
    - **removed**: name in ``existing_blob_shas`` but not in upstream.
      Returned in :attr:`FetchPlan.removed` for the caller to delete.

    Fragment fetches happen in parallel capped by
    :data:`_FETCH_CONCURRENCY`. With gating in steady state most ingest
    runs fetch fewer than 20 fragments (the typical weekly churn for
    Installomator), reducing both wall-clock time and the resolver fan-out
    that follows.

    :param ref: Git ref (branch, tag, or SHA). Defaults to
        ``$PATCHER_API_INSTALLOMATOR_REF`` or ``refs/heads/main``.
    :type ref: str | None
    :param client: Optional pre-configured ``httpx.AsyncClient``. If ``None``,
        a new client with a 60-second timeout is created and disposed.
    :type client: httpx.AsyncClient | None
    :param existing_blob_shas: Map of ``{name: blob_sha}`` already stored
        in the local DB. ``None`` (default) acts like an empty map — every
        upstream label is treated as new and fetched.
    :type existing_blob_shas: dict[str, str] | None
    :param force: When ``True``, fetch every upstream label regardless of
        stored SHA. Use after parser changes or when the resolver's
        coverage improves and you want all rows re-evaluated.
    :type force: bool
    :return: A :class:`FetchPlan` carrying fetched content, the full
        upstream SHA map, the set to remove, and per-bucket counts.
    :rtype: :class:`FetchPlan`
    :raises httpx.HTTPError: On tree-fetch failure (per-fragment errors
        are counted, not raised).
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=60.0)
    try:
        upstream = await _fetch_upstream_tree(ref, client=client)
        existing = existing_blob_shas or {}

        if force:
            changed_names = set(upstream)
            unchanged = 0
        else:
            changed_names = {name for name, sha in upstream.items() if existing.get(name) != sha}
            unchanged = len(upstream) - len(changed_names)

        removed = frozenset(existing) - frozenset(upstream)

        log.info(
            "Installomator tree: upstream=%d, changed=%d, unchanged=%d, removed=%d "
            "(force=%s, ref=%s)",
            len(upstream),
            len(changed_names),
            unchanged,
            len(removed),
            force,
            ref or _installomator_ref(),
        )

        if not changed_names:
            return FetchPlan(
                name_to_content={},
                name_to_blob_sha=upstream,
                removed=removed,
                unchanged=unchanged,
                missing=0,
                errored=0,
            )

        log.info(
            "Fetching %d Installomator label fragments (concurrency=%d)...",
            len(changed_names),
            _FETCH_CONCURRENCY,
        )

        semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)
        missing = errored = 0
        name_to_content: dict[str, str] = {}
        completed = 0
        total = len(changed_names)

        async def fetch_one(name: str) -> tuple[str, str | None, str]:
            nonlocal completed
            async with semaphore:
                try:
                    response = await client.get(_fragment_url(name, ref))
                    if response.status_code == 404:
                        outcome = (name, None, "missing")
                    else:
                        response.raise_for_status()
                        outcome = (name, response.text, "ok")
                except httpx.HTTPError as exc:
                    log.warning("Unexpected error fetching label %r: %s", name, exc)
                    outcome = (name, None, "errored")
            completed += 1
            if completed % _PROGRESS_EVERY == 0 or completed == total:
                log.info("Installomator fetch: %d/%d labels", completed, total)
            return outcome

        results = await asyncio.gather(*(fetch_one(name) for name in changed_names))
        for name, content, status in results:
            if status == "ok" and content is not None:
                name_to_content[name] = content
            elif status == "missing":
                missing += 1
            else:
                errored += 1

        log.info(
            "Installomator fetch complete: ok=%d, missing=%d, errored=%d",
            len(name_to_content),
            missing,
            errored,
        )

        return FetchPlan(
            name_to_content=name_to_content,
            name_to_blob_sha=upstream,
            removed=removed,
            unchanged=unchanged,
            missing=missing,
            errored=errored,
        )
    finally:
        if owns_client:
            await client.aclose()


async def ingest_installomator_labels(
    session: AsyncSession,
    name_to_content: dict[str, str],
    *,
    name_to_blob_sha: dict[str, str] | None = None,
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
    :param name_to_blob_sha: Optional map of ``{name: blob_sha}`` for the
        labels being ingested. When provided, the SHA is persisted in the
        ``blob_sha`` column so future ingests can gate. Lookups missing a
        SHA fall through to ``NULL``; existing callers that don't pass
        this kwarg behave exactly as before (no breakage in tests that
        construct ``name_to_content`` directly).
    :type name_to_blob_sha: dict[str, str] | None
    :return: ``(ingested, skipped, failed)`` — ingested is the count of
        labels successfully stored; skipped is the count filtered out by
        team-ID exclusion or empty parse; failed is the count that raised
        an unexpected exception during INSERT.
    :rtype: tuple[int, int, int]
    """
    blob_shas = name_to_blob_sha or {}
    ingested = skipped = failed = 0
    total = len(name_to_content)

    # One shared httpx.Client for all resolutions in this batch (resolution only)
    resolver_client = httpx.Client(timeout=30.0) if _RESOLVE_ON_INGEST else None

    # Set resolution limit
    resolve_semaphore = asyncio.Semaphore(_RESOLVE_CONCURRENCY)
    resolve_completed = 0

    async def resolve_one(
        name: str, content: str
    ) -> tuple[str, dict[str, Any] | None, str | None, str | None]:
        """
        Parse a label fragment and resolve its downloadURL + appNewVersion.

        Returns ``(name, parsed_or_None_if_skip, resolved_download_url, resolved_app_new_version)``.
        A ``parsed`` of ``None`` signals the persist phase should count this as skipped.
        """
        nonlocal resolve_completed
        async with resolve_semaphore:
            parsed = parse_fragment(content)
            if not parsed or parsed.get("expectedTeamID") in IGNORED_TEAMS:
                outcome = (name, None, None, None)
            else:
                raw_download_url = _scalar_for_column(parsed.get("downloadURL"))
                raw_app_new_version = _scalar_for_column(parsed.get("appNewVersion"))
                resolved_download_url, resolved_app_new_version = await asyncio.gather(
                    asyncio.to_thread(
                        _resolve_or_null, raw_download_url, resolver_client, is_url=True
                    ),
                    asyncio.to_thread(_resolve_or_null, raw_app_new_version, resolver_client),
                )
                outcome = (name, parsed, resolved_download_url, resolved_app_new_version)
        resolve_completed += 1
        if resolve_completed % _PROGRESS_EVERY == 0 or resolve_completed == total:
            log.info("Installomator resolve: %d/%d labels", resolve_completed, total)
        return outcome

    log.info(
        "Resolving %d Installomator labels (concurrency=%d, resolver=%s)...",
        total,
        _RESOLVE_CONCURRENCY,
        "enabled" if _RESOLVE_ON_INGEST else "disabled",
    )

    try:
        resolved_records = await asyncio.gather(
            *(resolve_one(name, content) for name, content in name_to_content.items())
        )

        log.info("Persisting %d Installomator label rows...", total)
        for name, parsed, resolved_download_url, resolved_app_new_version in resolved_records:
            if parsed is None:
                # Filtered in resolve_one (empty parse or excluded team ID).
                skipped += 1
                continue

            try:
                now = datetime.now(UTC)
                stmt = insert(InstallomatorLabel).values(
                    name=name,
                    display_name=_scalar_for_column(parsed.get("name")),
                    install_type=_scalar_for_column(parsed.get("type")),
                    package_id=_scalar_for_column(parsed.get("packageID")),
                    download_url=resolved_download_url,
                    expected_team_id=_scalar_for_column(parsed.get("expectedTeamID")),
                    app_new_version=resolved_app_new_version,
                    raw=parsed,
                    fragment=name_to_content[name],
                    blob_sha=blob_shas.get(name),
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
                        "fragment": stmt.excluded.fragment,
                        "blob_sha": stmt.excluded.blob_sha,
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
    finally:
        if resolver_client is not None:
            resolver_client.close()

    log.info(
        "Installomator ingest complete: ingested=%d, skipped=%d, failed=%d",
        ingested,
        skipped,
        failed,
    )

    return ingested, skipped, failed
