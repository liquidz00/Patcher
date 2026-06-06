"""
Match Jamf patch titles against the Patcher API catalog.

Used by :meth:`PatcherClient.fetch_patches` to populate
``PatchTitle.install_label`` with name-only :class:`Label` stubs for every
patch title that has an Installomator-tracked counterpart. The matching
algorithm itself (direct → normalized → fuzzy) is the same one
``InstallomatorClient.match()`` runs against ``Labels.txt``; only the
source of the slug set differs — here it comes from the API's stitched
catalog (which already includes every Installomator label, plus
cross-source enrichment for downstream consumers that query the API
directly).

When ``include_homebrew`` is set, the candidate slug set is widened to
include Homebrew Cask-sourced catalog entries (a second matching
dimension). Matches are then routed by provenance: an Installomator-sourced
slug populates ``install_label`` as before, while a Homebrew Cask-sourced
slug populates ``PatchTitle.homebrew_cask`` with a
:class:`~patcher.core.models.cask.CaskMatch`. A dual-source slug populates
both. This keeps the Installomator-only meaning of ``install_label``
intact rather than overloading it.

Module-level functions so the algorithm can be exercised standalone in
tests and (eventually) by other backends without going through
``PatcherClient``.
"""

from __future__ import annotations

import fnmatch
import json
import warnings
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from ..clients.jamf import JamfClient
from ..clients.patcher_api import App, PatcherAPIClient
from ..policy import IGNORED_TITLES
from .exceptions import APIResponseError, InstallomatorWarning
from .logger import LogMe
from .models.cask import CaskMatch
from .models.label import Label
from .models.patch import PatchTitle

DEFAULT_FUZZY_THRESHOLD = 85

DEFAULT_REVIEW_FILE = Path.home() / "Library/Application Support/Patcher/unmatched_apps.json"

# The ``/apps`` endpoint caps ``limit`` at 1000. Installomator's slug set fits
# in one page, but the Homebrew Cask set (~7k) does not, so callers paginate.
_CATALOG_PAGE_SIZE = 1000


def normalize_name(app_name: str) -> str:
    """Lowercase + strip spaces and dots — aligns Jamf app names with Installomator slugs."""
    return app_name.lower().replace(" ", "").replace(".", "")


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


def _make_stub(patch_title: str, slug: str) -> Label:
    """A name-only Label stub — enough to mark a match for downstream truthiness checks."""
    return Label(name=patch_title, installomator_label=slug)


def _make_cask_match(patch_title: str, app: App) -> CaskMatch:
    """
    Build a :class:`~patcher.core.models.cask.CaskMatch` coverage stub from a
    matched catalog ``App``.

    Carries the version and download URL the catalog already resolved so
    reports can surface them without a second lookup.

    :param patch_title: The patch title the match is attached to.
    :type patch_title: str
    :param app: The matched catalog record (a Homebrew Cask-sourced slug).
    :type app: :class:`~patcher.clients.patcher_api.App`
    :return: A Homebrew Cask coverage stub.
    :rtype: :class:`~patcher.core.models.cask.CaskMatch`
    """
    return CaskMatch(
        name=patch_title,
        token=app.slug,
        version=app.current_version,
        download_url=str(app.download_url) if app.download_url else None,
    )


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
    and still routes to both ``install_label`` and ``homebrew_cask``.

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
    include_homebrew: bool,
) -> bool:
    """
    Route matched slugs onto the patch title by source provenance.

    An Installomator-sourced slug appends a :class:`Label` stub to
    ``install_label``; a Homebrew Cask-sourced slug appends a
    :class:`~patcher.core.models.cask.CaskMatch` to ``homebrew_cask`` (only
    when ``include_homebrew`` is set). A dual-source slug appends to both.

    Homebrew attachment is gated on ``include_homebrew`` rather than on
    ``App.sources`` alone: dual-source apps are reachable even with the
    toggle off (they carry an Installomator label), and we must not populate
    ``homebrew_cask`` unless the caller opted in.

    :param patch_title: The title to mutate in place.
    :type patch_title: :class:`~patcher.core.models.patch.PatchTitle`
    :param slugs: Matched catalog slugs.
    :type slugs: list[str]
    :param apps_by_slug: Slug-to-``App`` map carrying provenance.
    :type apps_by_slug: dict[str, :class:`~patcher.clients.patcher_api.App`]
    :param include_homebrew: Whether to populate ``homebrew_cask``.
    :type include_homebrew: bool
    :return: True if any stub was attached.
    :rtype: bool
    """
    attached = False
    for slug in slugs:
        app = apps_by_slug.get(slug)
        if app is None:
            continue
        if "installomator" in app.sources:
            if patch_title.install_label is None:
                patch_title.install_label = []
            patch_title.install_label.append(_make_stub(patch_title.title, slug))
            attached = True
        if include_homebrew and "homebrew_cask" in app.sources:
            if patch_title.homebrew_cask is None:
                patch_title.homebrew_cask = []
            patch_title.homebrew_cask.append(_make_cask_match(patch_title.title, app))
            attached = True
    return attached


async def match_titles(
    patch_titles: list[PatchTitle],
    jamf: JamfClient,
    api: PatcherAPIClient,
    *,
    threshold: int = DEFAULT_FUZZY_THRESHOLD,
    review_file: Path | None = DEFAULT_REVIEW_FILE,
    include_homebrew: bool = False,
) -> None:
    """
    Match each :class:`~patcher.core.models.patch.PatchTitle` against the API
    catalog and populate coverage stubs for matches.

    Installomator-sourced matches populate ``install_label`` with
    :class:`Label` stubs. When ``include_homebrew`` is set, the candidate
    slug set also includes Homebrew Cask-sourced entries, and matches against
    those populate ``homebrew_cask`` with
    :class:`~patcher.core.models.cask.CaskMatch` stubs; a dual-source slug
    populates both fields.

    Mutates the input list in place. Titles that pattern-match
    :data:`~patcher.policy.IGNORED_TITLES` are skipped silently.

    :param patch_titles: The list of ``PatchTitle`` objects to match.
    :type patch_titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
    :param jamf: Configured :class:`~patcher.clients.jamf.JamfClient`. Used
        for :meth:`~patcher.clients.jamf.JamfClient.get_app_names` to
        retrieve per-title Jamf app-name lists.
    :param api: :class:`~patcher.clients.patcher_api.PatcherAPIClient`
        pointed at the catalog. Pages ``GET /apps`` for the ``installomator``
        source (and ``homebrew_cask`` when ``include_homebrew`` is set).
    :param threshold: Fuzzy-match score cutoff (rapidfuzz ratio, 0–100).
        Defaults to 85, matching ``InstallomatorClient``'s historical value.
    :type threshold: int
    :param review_file: Path to write a JSON file of unmatched patch titles
        for manual review. ``None`` disables the review-file write. Defaults
        to ``~/Library/Application Support/Patcher/unmatched_apps.json``.
    :type review_file: Path | None
    :param include_homebrew: If True, widen matching to the Homebrew Cask
        source and populate ``PatchTitle.homebrew_cask`` for Cask matches.
        Defaults to False (Installomator-only, the historical behavior).
    :type include_homebrew: bool
    """
    log = LogMe("matching")
    sources = ["installomator"]
    if include_homebrew:
        sources.append("homebrew_cask")
    log.debug(f"Starting API-backed matching (sources: {', '.join(sources)})")

    try:
        apps_by_slug = await _fetch_catalog_apps(api, sources=sources)
    except APIResponseError as exc:
        log.error(f"Failed to fetch catalog from Patcher API: {exc}")
        return

    available: set[str] = set(apps_by_slug)
    log.info(f"Loaded {len(available)} catalog slugs from Patcher API ({', '.join(sources)}).")

    try:
        software_titles = await jamf.get_app_names(patch_titles=patch_titles)
    except APIResponseError as exc:
        if getattr(exc, "not_found", False):
            return  # No app-name data — nothing to match.
        raise

    per_title_matches: dict[str, list[str]] = {}
    unmatched_apps: list[dict[str, Any]] = []

    for patch_title in patch_titles:
        if any(fnmatch.fnmatch(patch_title.title, pattern) for pattern in IGNORED_TITLES):
            log.info(f"Ignoring {patch_title.title}")
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
        if _attach_matches(patch_title, names, apps_by_slug, include_homebrew=include_homebrew):
            matched_count += 1

    matched_count += await _second_pass(
        unmatched_apps,
        available,
        patch_titles,
        apps_by_slug,
        threshold=threshold,
        include_homebrew=include_homebrew,
    )

    log.info(f"Matching process finished. {matched_count} PatchTitle objects were updated.")
    if unmatched_apps:
        source_label = "Installomator or Homebrew" if include_homebrew else "Installomator"
        log.warning(f"{len(unmatched_apps)} PatchTitle objects had no matches.")
        if review_file is not None:
            _save_unmatched(review_file, unmatched_apps)
        # Surface via the warnings system so callers can catch/escalate
        # independently of log level. The CLI shows these (simplefilter
        # "always", InstallomatorWarning); library callers can filter them out.
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
    include_homebrew: bool,
) -> int:
    """
    Retry unmatched titles using normalized + fuzzy matching against the
    patch title text, routing hits by source provenance.

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
    :param include_homebrew: Whether to populate ``homebrew_cask`` on hits.
    :type include_homebrew: bool
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
            if _attach_matches(
                patch_title, [target_name], apps_by_slug, include_homebrew=include_homebrew
            ):
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
