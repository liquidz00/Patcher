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

Module-level functions so the algorithm can be exercised standalone in
tests and (eventually) by other backends without going through
``PatcherClient``.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from ..clients.jamf import JamfClient
from ..clients.patcher_api import PatcherAPIClient
from .exceptions import APIResponseError
from .logger import LogMe
from .models.label import Label
from .models.patch import PatchTitle

_IGNORED_TITLES = [
    "Apple macOS *",
    "Oracle Java SE *",
    "Eclipse Temurin *",
    "Apple Safari",
    "Apple Xcode",
    "Microsoft Visual Studio",  # Support deprecated
]

DEFAULT_FUZZY_THRESHOLD = 85

DEFAULT_REVIEW_FILE = Path.home() / "Library/Application Support/Patcher/unmatched_apps.json"


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


async def match_titles(
    patch_titles: list[PatchTitle],
    jamf: JamfClient,
    api: PatcherAPIClient,
    *,
    threshold: int = DEFAULT_FUZZY_THRESHOLD,
    review_file: Path | None = DEFAULT_REVIEW_FILE,
) -> None:
    """
    Match each :class:`~patcher.core.models.patch.PatchTitle` against the API
    catalog and populate ``install_label`` with Label stubs for matches.

    Mutates the input list in place. Titles that pattern-match
    the module's ``_IGNORED_TITLES`` list are skipped silently.

    :param patch_titles: The list of ``PatchTitle`` objects to match.
    :type patch_titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
    :param jamf: Configured :class:`~patcher.clients.jamf.JamfClient`. Used
        for :meth:`~patcher.clients.jamf.JamfClient.get_app_names` to
        retrieve per-title Jamf app-name lists.
    :param api: :class:`~patcher.clients.patcher_api.PatcherAPIClient`
        pointed at the catalog. Used for one call: ``GET /apps?source=
        installomator&limit=1000``.
    :param threshold: Fuzzy-match score cutoff (rapidfuzz ratio, 0–100).
        Defaults to 85, matching ``InstallomatorClient``'s historical value.
    :type threshold: int
    :param review_file: Path to write a JSON file of unmatched patch titles
        for manual review. ``None`` disables the review-file write. Defaults
        to ``~/Library/Application Support/Patcher/unmatched_apps.json``.
    :type review_file: Path | None
    """
    log = LogMe("matching")
    log.debug("Starting API-backed Installomator matching")

    try:
        apps = await api.list_apps(source="installomator", limit=1000)
    except APIResponseError as exc:
        log.error(f"Failed to fetch catalog from Patcher API: {exc}")
        return

    available: set[str] = {app.slug for app in apps}
    log.info(f"Loaded {len(available)} Installomator-sourced slugs from Patcher API.")

    try:
        software_titles = await jamf.get_app_names(patch_titles=patch_titles)
    except APIResponseError as exc:
        if getattr(exc, "not_found", False):
            return  # No app-name data — nothing to match.
        raise

    per_title_matches: dict[str, list[str]] = {}
    unmatched_apps: list[dict[str, Any]] = []

    for patch_title in patch_titles:
        if any(fnmatch.fnmatch(patch_title.title, pattern) for pattern in _IGNORED_TITLES):
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
        stubs = [_make_stub(patch_title.title, name) for name in names]
        if patch_title.install_label is None:
            patch_title.install_label = []
        patch_title.install_label.extend(stubs)
        matched_count += 1

    matched_count += await _second_pass(
        unmatched_apps, available, patch_titles, threshold=threshold
    )

    log.info(f"Matching process finished. {matched_count} PatchTitle objects were updated.")
    if unmatched_apps:
        log.warning(f"{len(unmatched_apps)} PatchTitle objects had no matches.")
        if review_file is not None:
            _save_unmatched(review_file, unmatched_apps)


async def _second_pass(
    unmatched_apps: list[dict[str, Any]],
    available: set[str],
    patch_titles: list[PatchTitle],
    *,
    threshold: int,
) -> int:
    """Retry unmatched titles using normalized + fuzzy matching against the patch title text."""
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
            if patch_title.install_label is None:
                patch_title.install_label = []
            patch_title.install_label.append(_make_stub(patch_name, target_name))
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
