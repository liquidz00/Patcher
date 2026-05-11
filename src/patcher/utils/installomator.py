import asyncio
import fnmatch
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from rapidfuzz import fuzz, process

from ..client.api_client import ApiClient
from ..client.config_manager import ConfigManager
from ..models.label import Label
from ..models.patch import PatchTitle
from .exceptions import APIResponseError, PatcherError, ShellCommandError
from .logger import LogMe

IGNORED_TEAMS = ["Frydendal", "Media", "LL3KBL2M3A"]  # "LL3KBL2M3A" - lcadvancedvpnclient

# Installomator hosts a flat list of every label name in Labels.txt at the
# repo root. Parsing this file before fetching individual fragments lets us
# avoid the ~700-call directory-listing + mass-download fan-out that the
# previous implementation performed on first run.
_INSTALLOMATOR_RAW_BASE = (
    "https://raw.githubusercontent.com/Installomator/Installomator/refs/heads/main"
)
_LABELS_TXT_URL = f"{_INSTALLOMATOR_RAW_BASE}/Labels.txt"
_FRAGMENT_URL_TEMPLATE = f"{_INSTALLOMATOR_RAW_BASE}/fragments/labels/{{name}}.sh"


class Installomator:
    def __init__(self, concurrency: int | None = 5):
        """
        The Installomator class interacts with `Installomator <https://github.com/Installomator/Installomator>`_, a script used for automated software installations on macOS.

        This class provides methods for discovering, fetching, and matching Installomator labels to ``PatchTitle`` objects. Discovery uses the lightweight ``Labels.txt`` file at the Installomator repo root; individual ``.sh`` fragments are fetched lazily and only for matches.

        :param concurrency: Number of concurrent requests allowed for API operations. See :ref:`concurrency <concurrency>` in Usage docs.
        :type concurrency: int | None
        """
        self.log = LogMe(self.__class__.__name__)
        self.label_path = Path.home() / "Library/Application Support/Patcher/.labels"
        self.config = ConfigManager()
        self.api = ApiClient(config=self.config, concurrency=concurrency)
        self.threshold = 85
        self.review_file = Path.home() / "Library/Application Support/Patcher/unmatched_apps.json"

        # Session-scoped caches. `_available_names` holds the parsed Labels.txt
        # contents (a set of script names). `_labels_by_name` holds Label
        # objects keyed by script name as they are fetched.
        self._available_names: set[str] | None = None
        self._labels_by_name: dict[str, Label] = {}

    # ------------------------------------------------------------------ #
    # Parsing & label construction
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse(fragment: str) -> dict[str, Any]:
        """Parses the passed fragment string and returns dictionary of formatted key-values."""
        fragment = re.sub(r"^\w+\)\s*", "", fragment).strip()  # Remove opening key
        fragment = re.sub(r";;\s*$", "", fragment).strip()  # Remove trailing ;;

        data = {}
        lines = fragment.splitlines()

        # Regex patterns for parsing
        kv_pattern = re.compile(r'^(\w+)=(".*?"|\$\(.*?\)|\S+)')  # Key-value pairs
        array_pattern = re.compile(r"^(\w+)=\((.*?)\)$")  # Arrays

        for line in lines:
            line = line.strip()

            # Ignore comments and empty lines
            if line.startswith("#") or not line:
                continue

            # Match Bash array syntax
            array_match = array_pattern.match(line)
            if array_match:
                key, array_values = array_match.groups()
                # Split array values by spaces, accounting for potential quotes
                data[key] = re.findall(r'"(.*?)"|(\S+)', array_values)
                data[key] = [val[0] or val[1] for val in data[key]]
                continue

            kv_match = kv_pattern.match(line)
            if kv_match:
                key, value = kv_match.groups()
                # Strip surrounding quotes for quoted values
                value = value.strip('"')
                data[key] = value  # type: ignore
                continue

        return data

    def _build_label_from_content(self, content: str, script_name: str) -> Label | None:
        """Parse a fragment's raw .sh content into a ``Label`` object.

        Returns ``None`` if the fragment's expected Team ID is in
        :data:`IGNORED_TEAMS` or if Pydantic validation fails.
        """
        fragment_dict = self._parse(content)

        expected_team_id = fragment_dict.get("expectedTeamID")
        if expected_team_id in IGNORED_TEAMS:
            self.log.warning(f"Skipping label {script_name} (ignored Team ID: {expected_team_id})")
            return None

        try:
            return Label.from_dict(fragment_dict, installomatorLabel=script_name)
        except ValidationError as e:
            self.log.warning(
                f"Skipping invalid Installomator label: {script_name} due to validation error: {e}"
            )
            return None

    # ------------------------------------------------------------------ #
    # Discovery + fetch (public API)
    # ------------------------------------------------------------------ #

    async def list_available_labels(self) -> set[str]:
        """
        Return the set of every label name currently available in Installomator.

        Fetches and parses :data:`_LABELS_TXT_URL`. The result is cached on the instance for the session; subsequent calls do not re-fetch.

        :return: A set of label script names (e.g. ``{"googlechrome", "1password8", ...}``).
        :rtype: set[str]
        :raises PatcherError: If the labels file cannot be fetched.
        """
        if self._available_names is not None:
            return self._available_names

        self.log.debug(f"Fetching Installomator Labels.txt from {_LABELS_TXT_URL}")
        try:
            content = await self.api.execute(["/usr/bin/curl", "-fsSL", _LABELS_TXT_URL])
        except ShellCommandError as e:
            raise PatcherError("Unable to retrieve Installomator Labels.txt", error_msg=str(e))

        # Labels.txt is one label name per line. Strip whitespace, drop blanks
        # and comments (lines starting with '#'), normalize to lowercase to
        # match the rest of the matching pipeline.
        names = {
            line.strip().lower()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        self._available_names = names
        self.log.info(f"Discovered {len(names)} Installomator labels.")
        return names

    async def get_label(self, name: str) -> Label | None:
        """
        Fetch and parse a single Installomator label by script name.

        Lookup order:

        1. Instance cache (``self._labels_by_name``)
        2. On-disk cache (``~/Library/Application Support/Patcher/.labels/<name>.sh``)
        3. HTTP fetch from :data:`_FRAGMENT_URL_TEMPLATE`

        :param name: The Installomator script name (e.g. ``"googlechrome"``).
            Case-insensitive; normalized to lowercase before lookup.
        :type name: str
        :return: The constructed ``Label`` object, or ``None`` if the fragment
            cannot be fetched, is ignored by Team ID, or fails validation.
        :rtype: :class:`~patcher.models.label.Label` | None
        """
        key = name.lower()
        if key in self._labels_by_name:
            return self._labels_by_name[key]

        # On-disk cache
        cache_path = self.label_path / f"{key}.sh"
        if cache_path.exists():
            try:
                content = cache_path.read_text()
                label = self._build_label_from_content(content, key)
                if label is not None:
                    self._labels_by_name[key] = label
                return label
            except OSError as e:
                self.log.warning(
                    f"Could not read cached fragment {cache_path}; will refetch. Details: {e}"
                )

        # HTTP fetch — `-f` makes curl exit non-zero on 4xx/5xx so we don't
        # silently parse "404: Not Found" bodies as labels.
        url = _FRAGMENT_URL_TEMPLATE.format(name=key)
        self.log.debug(f"Fetching Installomator fragment from {url}")
        try:
            content = await self.api.execute(["/usr/bin/curl", "-fsSL", url])
        except ShellCommandError as e:
            self.log.warning(f"Failed to fetch Installomator fragment for '{name}': {e}")
            return None

        if not content:
            return None

        # Best-effort cache write — failure here doesn't prevent returning the label
        try:
            self.label_path.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(content)
        except OSError as e:
            self.log.warning(f"Could not write fragment cache to {cache_path}: {e}")

        label = self._build_label_from_content(content, key)
        if label is not None:
            self._labels_by_name[key] = label
        return label

    async def get_labels(self, names: Iterable[str] | None = None) -> list[Label]:
        """
        Fetch and parse multiple Installomator labels in parallel.

        :param names: Specific label script names to fetch. If ``None`` (the
            default), fetches **every** label listed in :data:`_LABELS_TXT_URL`
            — typically ~700 HTTP calls on first run, served from disk cache
            on subsequent runs. Prefer passing a concrete name list when you
            know what you need.
        :type names: Iterable[str] | None
        :return: List of successfully parsed ``Label`` objects. Labels that
            fail to fetch, hit an ignored Team ID, or fail validation are
            silently omitted (warnings are logged).
        :rtype: list[:class:`~patcher.models.label.Label`]
        """
        if names is None:
            names_iter = await self.list_available_labels()
        else:
            names_iter = {n.lower() for n in names}

        if not names_iter:
            return []

        tasks = [self.get_label(name) for name in names_iter]
        results = await asyncio.gather(*tasks)
        return [label for label in results if label is not None]

    # ------------------------------------------------------------------ #
    # Matching helpers (mostly unchanged from the prior implementation)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize(app_name: str) -> str:
        """Normalizes app names to better match Installomator labels (e.g. nodejs)."""
        return app_name.lower().replace(" ", "").replace(".", "")

    def _match_directly(self, app_names: list[str], available: set[str]) -> list[str]:
        """Direct and normalized name matching against the available script-name set."""
        matched: list[str] = []
        for app_name in app_names:
            lower = app_name.lower()
            if lower in available and lower not in matched:
                matched.append(lower)
            normalized = self._normalize(app_name)
            if normalized in available and normalized not in matched:
                matched.append(normalized)
        return matched

    def _match_fuzzy(self, app_names: list[str], available: set[str]) -> list[str]:
        """Fuzzy match (rapidfuzz ratio) against the available script-name set."""
        matched: list[str] = []
        choices = list(available)
        for app_name in app_names:
            result = process.extractOne(app_name.lower(), choices, scorer=fuzz.ratio)  # type: ignore
            if result:
                best_match, score, _ = result
                if best_match and score >= self.threshold and best_match not in matched:
                    matched.append(best_match)
        return matched

    async def _second_pass(
        self,
        unmatched_apps: list[dict[str, Any]],
        available: set[str],
        patch_titles: list[PatchTitle],
    ) -> int:
        """Retry unmatched apps using normalized + fuzzy matching on the patch title itself."""
        matched_count = 0
        still_unmatched: list[dict[str, Any]] = []

        for entry in unmatched_apps:
            patch_name = entry["Patch"]
            normalized_patch = self._normalize(patch_name)
            patch_title = next((pt for pt in patch_titles if pt.title == patch_name), None)

            target_name: str | None = None
            if normalized_patch in available:
                target_name = normalized_patch
                self.log.debug(f"Second-pass normalized match for {patch_name} → {target_name}")
            else:
                result = process.extractOne(normalized_patch, list(available), scorer=fuzz.ratio)  # type: ignore
                if result:
                    best_match, score, _ = result
                    if best_match and score >= self.threshold:
                        target_name = best_match
                        self.log.debug(
                            f"Second-pass fuzzy match for {patch_name} → {target_name} (score {score})"
                        )

            if target_name and patch_title is not None:
                label = await self.get_label(target_name)
                if label is not None:
                    patch_title.install_label.append(label)
                    matched_count += 1
                    continue

            still_unmatched.append(entry)

        unmatched_apps[:] = still_unmatched
        return matched_count

    def _save_unmatched_apps(self, unmatched_apps: list[dict[str, Any]]) -> None:
        """Saves unmatched apps to a JSON file for later review."""
        self.review_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.review_file, "w") as file:
            json.dump(unmatched_apps, file, indent=4)  # type: ignore

    # ------------------------------------------------------------------ #
    # match() — orchestrator
    # ------------------------------------------------------------------ #

    async def match(self, patch_titles: list[PatchTitle]) -> None:
        """
        Match Jamf patch titles to Installomator labels.

        Flow:

        1. Fetch the set of available label script names via :meth:`list_available_labels` (one HTTP call).
        2. Pull each patch title's associated app names via :meth:`~patcher.client.api_client.ApiClient.get_app_names`.
        3. Match each title's app names against the available script names — direct, then normalized, then fuzzy.
        4. Fetch the matched label fragments in parallel via :meth:`get_labels` and attach them to ``PatchTitle.install_label``.
        5. Run a second-pass attempt on still-unmatched titles, keyed on the patch title text itself.
        6. Persist any remaining unmatched apps to ``unmatched_apps.json`` for manual review.

        :param patch_titles: The list of ``PatchTitle`` objects to match. Each
            successfully matched title has its ``install_label`` attribute
            extended in place.
        :type patch_titles: list[:class:`~patcher.models.patch.PatchTitle`]
        """
        self.log.debug("Starting label-patch title matching process.")

        IGNORED_TITLES = [  # noqa: N806
            "Apple macOS *",
            "Oracle Java SE *",
            "Eclipse Temurin *",
            "Apple Safari",
            "Apple Xcode",
            "Microsoft Visual Studio",  # Support deprecated
        ]

        try:
            software_titles = await self.api.get_app_names(patch_titles=patch_titles)
        except APIResponseError as e:
            if getattr(e, "not_found", False):
                return  # Exit early, do not stop process
            raise  # Non-404 errors get re-raised

        available = await self.list_available_labels()

        # Compute matches per patch title, gathering all unique script names we'll need
        per_title_matches: dict[str, list[str]] = {}
        unmatched_apps: list[dict[str, Any]] = []

        for patch_title in patch_titles:
            if any(fnmatch.fnmatch(patch_title.title, pattern) for pattern in IGNORED_TITLES):
                self.log.info(f"Ignoring {patch_title.title}")
                continue

            app_name_entry = next(
                (entry for entry in software_titles if entry["Patch"] == patch_title.title), None
            )
            app_names = app_name_entry["App Names"] if app_name_entry else []

            if not app_names:
                self.log.warning(f"Skipping {patch_title.title} - No app names found.")
                unmatched_apps.append({"Patch": patch_title.title, "App Names": []})
                continue

            matched_names = self._match_directly(app_names, available) or self._match_fuzzy(
                app_names, available
            )

            if matched_names:
                per_title_matches[patch_title.title] = matched_names
            else:
                unmatched_apps.append({"Patch": patch_title.title, "App Names": app_names})

        # Single batched fetch for every distinct matched script name
        all_matched_names: set[str] = {n for names in per_title_matches.values() for n in names}
        if all_matched_names:
            await self.get_labels(all_matched_names)

        matched_count = 0
        for patch_title in patch_titles:
            names = per_title_matches.get(patch_title.title)
            if not names:
                continue
            labels_for_title = [self._labels_by_name[n] for n in names if n in self._labels_by_name]
            if labels_for_title:
                patch_title.install_label.extend(labels_for_title)
                matched_count += 1

        # Second pass on unmatched: try normalized patch title + fuzzy
        matched_count += await self._second_pass(unmatched_apps, available, patch_titles)

        self._save_unmatched_apps(unmatched_apps)

        self.log.info(
            f"Matching process finished. {matched_count} PatchTitle objects were updated."
        )
        if unmatched_apps:
            self.log.warning(
                f"{len(unmatched_apps)} PatchTitle objects had no matches. Review: {self.review_file}"
            )
