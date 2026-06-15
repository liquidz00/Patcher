"""
Match Jamf patch titles against the Patcher API catalog (direct → normalized → fuzzy).

A matched slug is recorded on ``PatchTitle.sources`` under every source its
catalog ``App`` carries, so coverage from all sources (including AutoPkg and
Jamf App Installers) surfaces for free. Module-level functions so the algorithm
can be exercised standalone in tests.
"""

from __future__ import annotations

import fnmatch
import json
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from ..catalog._normalize import normalize_name
from ..clients.jamf import JamfClient
from ..clients.patcher_api import App, PatcherAPIClient
from ..policy import IGNORED_TITLES
from .exceptions import APIResponseError, InstallomatorWarning
from .logger import LogMe
from .models.patch import PatchTitle

DEFAULT_FUZZY_THRESHOLD = 85

DEFAULT_REVIEW_FILE = Path.home() / "Library/Application Support/Patcher/unmatched_apps.json"

# The ``/apps`` endpoint caps ``limit`` at 1000. Installomator's slug set fits
# in one page, but the Homebrew Cask set (~7k) does not, so callers paginate.
_CATALOG_PAGE_SIZE = 1000

# Sources we can page /apps by as match candidates; autopkg/jai ride along on matched slugs.
_FETCHABLE_SOURCES = ("installomator", "homebrew_cask")
_SOURCE_DISPLAY = {"installomator": "Installomator", "homebrew_cask": "Homebrew"}


def match_directly(app_names: list[str], available: set[str]) -> list[str]:
    """Direct + normalized name matches against the available slug set."""
    matched: list[str] = []
    for app_name in app_names:
        lower = app_name.lower()
        if lower in available and lower not in matched:
            matched.append(lower)
        normalized = normalize_name(app_name)
        if normalized in available and normalized not in matched:
            matched.append(normalized)
    return matched


def match_fuzzy(
    app_names: list[str],
    available: set[str],
    *,
    threshold: int = DEFAULT_FUZZY_THRESHOLD,
) -> list[str]:
    """Fuzzy (rapidfuzz ratio) match against the available slug set."""
    matched: list[str] = []
    choices = list(available)
    for app_name in app_names:
        result = process.extractOne(app_name.lower(), choices, scorer=fuzz.ratio)  # type: ignore
        if result:
            best_match, score, _ = result
            if best_match and score >= threshold and best_match not in matched:
                matched.append(best_match)
    return matched


async def _fetch_catalog_apps(
    api: PatcherAPIClient,
    *,
    sources: list[str],
) -> dict[str, App]:
    """
    Fetch every catalog ``App`` carrying any of the given source tokens,
    keyed by slug.

    Pages through ``GET /apps`` per source (the endpoint caps ``limit`` at
    :data:`_CATALOG_PAGE_SIZE`) until a short page signals the end. The
    returned ``App.sources`` is authoritative for provenance regardless of
    which source query surfaced the row, so a dual-source app is stored once
    and still records every source it carries.

    :param api: Catalog client.
    :type api: :class:`~patcher.clients.patcher_api.PatcherAPIClient`
    :param sources: Source tokens to fetch (e.g. ``["installomator"]`` or
        ``["installomator", "homebrew_cask"]``).
    :type sources: list[str]
    :return: Mapping of slug to its catalog ``App``.
    :rtype: dict[str, :class:`~patcher.clients.patcher_api.App`]
    """
    by_slug: dict[str, App] = {}
    for source in sources:
        offset = 0
        while True:
            page = await api.list_apps(source=source, limit=_CATALOG_PAGE_SIZE, offset=offset)
            for app in page:
                by_slug.setdefault(app.slug, app)
            if len(page) < _CATALOG_PAGE_SIZE:
                break
            offset += _CATALOG_PAGE_SIZE
    return by_slug


def _attach_matches(
    patch_title: PatchTitle,
    slugs: list[str],
    apps_by_slug: dict[str, App],
    *,
    enabled: set[str] | None,
) -> bool:
    """
    Record matched slugs on the title's ``sources`` map by provenance.

    Each slug is bucketed under every source its catalog ``App`` carries that is
    also in ``enabled``, so a dual-source slug appears under each enabled source
    and coverage the catalog already knows about (AutoPkg, Jamf App Installers)
    surfaces without a second lookup. ``enabled=None`` disables gating entirely.

    :param patch_title: The title to mutate in place.
    :type patch_title: :class:`~patcher.core.models.patch.PatchTitle`
    :param slugs: Matched catalog slugs.
    :type slugs: list[str]
    :param apps_by_slug: Slug-to-``App`` map carrying provenance.
    :type apps_by_slug: dict[str, :class:`~patcher.clients.patcher_api.App`]
    :param enabled: Source tokens permitted on the map, or ``None`` for no gating.
    :type enabled: set[str] | None
    :return: True if any source bucket gained a slug.
    :rtype: bool
    """
    if patch_title.sources is None:
        patch_title.sources = {}
    attached = False
    for slug in slugs:
        app = apps_by_slug.get(slug)
        if app is None:
            continue
        for source in app.sources:
            if enabled is not None and source not in enabled:
                continue
            bucket = patch_title.sources.setdefault(source, [])
            if slug not in bucket:
                bucket.append(slug)
                attached = True
    return attached


async def match_titles(
    patch_titles: list[PatchTitle],
    jamf: JamfClient,
    api: PatcherAPIClient,
    *,
    threshold: int = DEFAULT_FUZZY_THRESHOLD,
    review_file: Path | None = DEFAULT_REVIEW_FILE,
    enabled_sources: set[str] | None = None,
    ignored_titles: list[str] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    """
    Match each :class:`~patcher.core.models.patch.PatchTitle` against the API
    catalog and record matched slugs on its ``sources`` map.

    ``enabled_sources`` is the set of catalog source tokens permitted for this
    run. The candidate set is paged from the fetchable subset of those tokens
    (Installomator, Homebrew Cask), and a matched slug is recorded under every
    *enabled* source its catalog ``App`` carries, so AutoPkg and Jamf App
    Installers coverage surfaces for free when enabled. ``None`` (the default)
    disables gating: candidates page from both fetchable sources and every
    source on a matched slug is recorded.

    Each title is matched deterministically first by its ``name_id`` (Jamf
    softwareTitleNameId) against the catalog's jamf-index; titles without a
    code, or whose code isn't indexed, fall back to direct/fuzzy name matching.

    Mutates the input list in place. Titles that pattern-match
    :data:`~patcher.policy.IGNORED_TITLES` (plus any caller-supplied
    ``ignored_titles``) are skipped silently.

    :param patch_titles: The list of ``PatchTitle`` objects to match.
    :type patch_titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
    :param jamf: Configured :class:`~patcher.clients.jamf.JamfClient`. Used
        for :meth:`~patcher.clients.jamf.JamfClient.get_app_names` to
        retrieve per-title Jamf app-name lists.
    :param api: :class:`~patcher.clients.patcher_api.PatcherAPIClient`
        pointed at the catalog. Pages ``GET /apps`` for each fetchable enabled
        source (``installomator`` and/or ``homebrew_cask``).
    :param threshold: Fuzzy-match score cutoff (rapidfuzz ratio, 0–100).
        Defaults to 85, matching ``InstallomatorClient``'s historical value.
    :type threshold: int
    :param review_file: Path to write a JSON file of unmatched patch titles
        for manual review. ``None`` disables the review-file write. Defaults
        to ``~/Library/Application Support/Patcher/unmatched_apps.json``.
    :type review_file: Path | None
    :param enabled_sources: Catalog source tokens permitted for this run.
        Gates both the candidate set (fetchable subset) and which sources are
        recorded on each title. ``None`` (default) disables gating.
    :type enabled_sources: set[str] | None
    :param ignored_titles: Extra Jamf-title skip patterns (``fnmatch`` syntax)
        merged with the built-in :data:`~patcher.policy.IGNORED_TITLES`. Lets
        callers skip titles managed out-of-band without editing policy.
    :type ignored_titles: list[str] | None
    :param progress_callback: Optional ``(processed, total)`` callback invoked
        once per title, letting a caller drive a progress display without this
        module depending on any UI. The CLI passes a Rich-backed callback.
    :type progress_callback: Callable[[int, int], None] | None
    """
    log = LogMe("matching")
    ignore_patterns = [*IGNORED_TITLES, *(ignored_titles or [])]
    if enabled_sources is None:
        fetch_sources = list(_FETCHABLE_SOURCES)
    else:
        fetch_sources = [s for s in _FETCHABLE_SOURCES if s in enabled_sources]
    log.debug(f"Starting API-backed matching (sources: {', '.join(fetch_sources)})")

    try:
        apps_by_slug = await _fetch_catalog_apps(api, sources=fetch_sources)
    except APIResponseError as exc:
        log.error(f"Failed to fetch catalog from Patcher API: {exc}")
        return

    available: set[str] = set(apps_by_slug)
    log.info(
        f"Loaded {len(available)} catalog slugs from Patcher API ({', '.join(fetch_sources)})."
    )

    try:
        jamf_index = await api.get_jamf_index()
    except APIResponseError as exc:
        log.warning(f"Jamf index unavailable; using fuzzy matching only: {exc}")
        jamf_index = {}

    try:
        software_titles = await jamf.get_app_names(patch_titles=patch_titles)
    except APIResponseError as exc:
        if getattr(exc, "not_found", False):
            return  # No app-name data — nothing to match.
        raise

    per_title_matches: dict[str, list[str]] = {}
    unmatched_apps: list[dict[str, Any]] = []

    total = len(patch_titles)
    for index, patch_title in enumerate(patch_titles, start=1):
        if progress_callback is not None:
            progress_callback(index, total)
        if any(fnmatch.fnmatch(patch_title.title, pattern) for pattern in ignore_patterns):
            log.info(f"Ignoring {patch_title.title}")
            continue

        # Deterministic match first: name_id maps to slugs exactly, restricted to the fetched set so misses fall through to fuzzy.
        if patch_title.name_id:
            index_slugs = [s for s in jamf_index.get(patch_title.name_id, []) if s in available]
            if index_slugs:
                per_title_matches[patch_title.title] = index_slugs
                continue

        app_name_entry = next(
            (entry for entry in software_titles if entry["Patch"] == patch_title.title), None
        )
        app_names = app_name_entry["App Names"] if app_name_entry else []

        if not app_names:
            log.warning(f"Skipping {patch_title.title} - No app names found.")
            unmatched_apps.append({"Patch": patch_title.title, "App Names": []})
            continue

        matched_names = match_directly(app_names, available) or match_fuzzy(
            app_names, available, threshold=threshold
        )

        if matched_names:
            per_title_matches[patch_title.title] = matched_names
        else:
            unmatched_apps.append({"Patch": patch_title.title, "App Names": app_names})

    matched_count = 0
    for patch_title in patch_titles:
        names = per_title_matches.get(patch_title.title)
        if not names:
            continue
        if _attach_matches(patch_title, names, apps_by_slug, enabled=enabled_sources):
            matched_count += 1

    matched_count += await _second_pass(
        unmatched_apps,
        available,
        patch_titles,
        apps_by_slug,
        threshold=threshold,
        enabled_sources=enabled_sources,
    )

    log.info(f"Matching process finished. {matched_count} PatchTitle objects were updated.")
    if unmatched_apps:
        source_label = " or ".join(_SOURCE_DISPLAY.get(s, s) for s in fetch_sources) or "catalog"
        log.warning(f"{len(unmatched_apps)} PatchTitle objects had no matches.")
        if review_file is not None:
            _save_unmatched(review_file, unmatched_apps)
        # Use warnings (not logging) so callers can catch/filter these independently of log level.
        warnings.warn(
            f"{len(unmatched_apps)} patch title(s) had no {source_label} match. "
            f"See {review_file} for the list."
            if review_file is not None
            else f"{len(unmatched_apps)} patch title(s) had no {source_label} match.",
            InstallomatorWarning,
            stacklevel=2,
        )


async def _second_pass(
    unmatched_apps: list[dict[str, Any]],
    available: set[str],
    patch_titles: list[PatchTitle],
    apps_by_slug: dict[str, App],
    *,
    threshold: int,
    enabled_sources: set[str] | None,
) -> int:
    """
    Retry unmatched titles using normalized + fuzzy matching against the
    patch title text, recording hits by source provenance.

    :param unmatched_apps: Mutable list of unmatched entries; matched ones
        are removed in place.
    :type unmatched_apps: list[dict[str, Any]]
    :param available: Candidate slug set to match against.
    :type available: set[str]
    :param patch_titles: The titles being matched.
    :type patch_titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
    :param apps_by_slug: Slug-to-``App`` map carrying provenance.
    :type apps_by_slug: dict[str, :class:`~patcher.clients.patcher_api.App`]
    :param threshold: Fuzzy-match score cutoff.
    :type threshold: int
    :param enabled_sources: Source tokens permitted on the map, or ``None``.
    :type enabled_sources: set[str] | None
    :return: Count of titles updated in this pass.
    :rtype: int
    """
    log = LogMe("matching")
    matched_count = 0
    still_unmatched: list[dict[str, Any]] = []

    for entry in unmatched_apps:
        patch_name = entry["Patch"]
        normalized_patch = normalize_name(patch_name)
        patch_title = next((pt for pt in patch_titles if pt.title == patch_name), None)

        target_name: str | None = None
        if normalized_patch in available:
            target_name = normalized_patch
            log.debug(f"Second-pass normalized match for {patch_name} → {target_name}")
        else:
            result = process.extractOne(normalized_patch, list(available), scorer=fuzz.ratio)  # type: ignore
            if result:
                best_match, score, _ = result
                if best_match and score >= threshold:
                    target_name = best_match
                    log.debug(
                        f"Second-pass fuzzy match for {patch_name} → {target_name} (score {score})"
                    )

        if target_name and patch_title is not None:
            if _attach_matches(patch_title, [target_name], apps_by_slug, enabled=enabled_sources):
                matched_count += 1
                continue

        still_unmatched.append(entry)

    unmatched_apps[:] = still_unmatched
    return matched_count


def _save_unmatched(review_file: Path, unmatched_apps: list[dict[str, Any]]) -> None:
    """Persist unmatched titles to ``review_file`` as a JSON list."""
    review_file.parent.mkdir(parents=True, exist_ok=True)
    with open(review_file, "w") as file:
        json.dump(unmatched_apps, file, indent=4)
