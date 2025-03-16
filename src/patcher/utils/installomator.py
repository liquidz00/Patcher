import asyncio
import fnmatch
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from rapidfuzz import fuzz, process

from ..client.api_client import ApiClient
from ..client.config_manager import ConfigManager
from ..models.fragment import Fragment
from ..models.label import Label
from ..models.patch import PatchTitle
from .exceptions import APIResponseError, PatcherError, ShellCommandError
from .logger import LogMe

IGNORED_TEAMS = ["Frydendal", "Media", "LL3KBL2M3A"]  # "LL3KBL2M3A" - lcadvancedvpnclient


class Installomator:
    def __init__(self, concurrency: Optional[int] = 5):
        """
        The Installomator class interacts with `Installomator <https://github.com/Installomator/Installomator>`_, a script used for automated software installations on macOS.

        This class provides methods for fetching, parsing, and matching Installomator labels to ``PatchTitle`` objects using direct or fuzzy matching.

        :param concurrency: Number of concurrent requests allowed for API operations. See :ref:`concurrency <concurrency>` in Usage docs.
        :type concurrency: :py:obj:`~typing.Optional` [:py:class:`int`]
        """
        self.log = LogMe(self.__class__.__name__)
        self.label_path = Path.home() / "Library/Application Support/Patcher/.labels"
        self.config = ConfigManager()
        self.api = ApiClient(config=self.config, concurrency=concurrency)
        self.threshold = 85
        self.review_file = Path.home() / "Library/Application Support/Patcher/unmatched_apps.json"

        self._labels: Optional[List[Label]] = None
        self._fragments: Optional[List[Fragment]] = None

    @staticmethod
    def _validate_labels(value: List[Any]) -> List[Label]:
        """Validates the provided value is a list of ``Label`` objects."""
        if not isinstance(value, list):
            raise PatcherError("Value provided is not a list of Label objects.", value=value)

        validated_labels = [item for item in value if isinstance(item, Label)]
        if not validated_labels:
            raise PatcherError("List provided does not contain any valid Label objects.")

        return validated_labels

    async def _save(self, file_name: str, download_url: str, file_path: Path) -> bool:
        """Saves raw Installomator fragments to specified file path. Defaults to ``self.label_path`` if no path is provided."""
        file_path = file_path or self.label_path
        self.log.debug(f"Attempting to download Installomator fragments to {file_path}")
        try:
            file_content = await self.api.execute(["/usr/bin/curl", "-s", download_url])
        except ShellCommandError as e:
            self.log.error(f"Unable to download Installomator fragment as expected. Details: {e}")
            return False

        try:
            with open(file_path, "w") as f:
                f.write(file_content)
            self.log.info(f"Downloaded {file_name} to {file_path} successfully.")
            return True
        except OSError as e:
            self.log.error(f"Could not write to {file_path}. Details: {e}")
            return False

    @staticmethod
    def _parse(fragment: str) -> Dict[str, Any]:
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

    async def _fetch_fragments(self) -> List[Fragment]:
        """Fetches Installomator fragments via GitHub API."""
        installomator_url = (
            "https://api.github.com/repos/Installomator/Installomator/contents/fragments/labels"
        )
        try:
            response = await self.api.fetch_json(installomator_url)
            # Cache fragments locally
            fragments = [Fragment(**item) for item in response]
            self._fragments = fragments
            return fragments
        except (APIResponseError, ValidationError) as e:
            raise PatcherError(
                "Unable to retrieve Installomator fragments as expected.", error_msg=str(e)
            )

    async def _create_label_dir(self, fragments: List[Fragment]) -> bool:
        """Creates label directory to save raw Installomator fragments locally."""
        if not self.label_path.exists():
            self.label_path.mkdir(parents=True, exist_ok=True)

        tasks = []
        for fragment in fragments:
            save_path = self.label_path / fragment.name
            if not save_path.exists():
                tasks.append(
                    self._save(
                        file_name=fragment.name,
                        download_url=fragment.download_url,
                        file_path=save_path,
                    )
                )

        results = await asyncio.gather(*tasks)
        return all(result is True for result in results)

    async def _build_labels(self) -> List[Label]:
        """Builds list of ``Label`` objects from parsing ``self.label_path``."""
        labels = []
        for file_path in self.label_path.glob("*.sh"):
            content = file_path.read_text()
            fragment_dict = self._parse(content)

            expected_team_id = fragment_dict.get("expectedTeamID")
            if expected_team_id in IGNORED_TEAMS:
                self.log.warning(
                    f"Skipping label {file_path.stem} (ignored Team ID: {expected_team_id})"
                )
                continue  # skip this label entirely

            try:
                label = Label.from_dict(
                    fragment_dict, installomatorLabel=file_path.stem.split(".")[0]
                )
                labels.append(label)
            except ValidationError as e:
                self.log.warning(
                    f"Skipping invalid Installomator label: {file_path.name} due to validation error: {e}"
                )
                continue  # Skip problematic label but continue

        return labels

    @staticmethod
    def _normalize(app_name: str) -> str:
        """Normalizes app names to better match Installomator labels (e.g. nodejs)."""
        return app_name.lower().replace(" ", "").replace(".", "")

    def _match_directly(self, app_names: List[str], label_lookup: Dict[str, Label]) -> List[Label]:
        """Attempts direct and normalized name matching."""
        matched_labels = []
        for app_name in app_names:
            normalized_name = self._normalize(app_name)
            if app_name.lower() in label_lookup:
                matched_labels.append(label_lookup[app_name.lower()])
            if normalized_name in label_lookup:
                matched_labels.append(label_lookup[normalized_name])
        return matched_labels

    def _match_fuzzy(self, app_names: List[str], label_lookup: Dict[str, Label]) -> List[Label]:
        """Attempts fuzzy matching if no direct match is found."""
        matched_labels = []
        for app_name in app_names:
            result = process.extractOne(app_name.lower(), list(label_lookup.keys()), scorer=fuzz.ratio)  # type: ignore
            if result:
                best_match, score, _ = result
                if best_match and score >= self.threshold:
                    matched_labels.append(label_lookup[best_match])
        return matched_labels

    def _second_pass(
        self,
        unmatched_apps: List[Dict[str, Any]],
        label_lookup: Dict[str, Label],
        patch_titles: List[PatchTitle],
    ) -> int:
        """Attempts to match previously unmatched apps by normalized ``PatchTitle.title`` and fuzzy search."""
        matched_count = 0
        still_unmatched = []

        for entry in unmatched_apps:
            patch_name = entry["Patch"]
            normalized_patch = self._normalize(patch_name)
            patch_title = next((pt for pt in patch_titles if pt.title == patch_name), None)

            if normalized_patch in label_lookup:
                if patch_title:
                    patch_title.install_label.append(label_lookup[normalized_patch])
                    self.log.debug(
                        f"Second-pass normalized match for {patch_name} → {normalized_patch}"
                    )
                    matched_count += 1
                continue

            result = process.extractOne(normalized_patch, list(label_lookup.keys()), scorer=fuzz.ratio)  # type: ignore
            if result:
                best_match, score, _ = result
                if best_match and score >= self.threshold:
                    if patch_title:
                        patch_title.install_label.append(label_lookup[best_match])
                        self.log.debug(
                            f"Second-pass fuzzy match for {patch_name} → {best_match} (Score: {score})"
                        )
                        matched_count += 1
                    continue

            still_unmatched.append(entry)

        unmatched_apps[:] = still_unmatched
        return matched_count

    def _save_unmatched_apps(self, unmatched_apps: List[Dict[str, Any]]) -> None:
        """Saves unmatched apps to a JSON file for later review."""
        self.review_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.review_file, "w") as file:
            json.dump(unmatched_apps, file, indent=4)  # type: ignore

    async def get_labels(self) -> List[Label]:
        """
        Builds ``Label`` objects after collecting ``Fragment`` objects from GitHub API.

        :return: The compiled list of ``Label`` objects.
        :rtype: :py:obj:`~typing.List` [:class:`~patcher.models.label.Label`]
        """
        if self._labels is None:
            fragments = await self._fetch_fragments()
            await self._create_label_dir(fragments)
            self._labels = await self._build_labels()
        return self._labels

    async def match(self, patch_titles: List[PatchTitle]) -> None:
        """
        Matches Installomator labels to ``PatchTitle`` objects using direct mapping and fuzzy matching.

        - Uses multiple app names from :meth:`~patcher.client.api_client.ApiClient.get_app_names`
        - Matches labels directly by name by default
        - Applies fuzzy matching as a fallback if direct matching fails
        - Updates :attr:`~patcher.models.patch.PatchTitle.install_label` with matched labels

        :param patch_titles: The list of ``PatchTitle`` objects to match with ``Label`` objects.
        :type patch_titles: :py:obj:`~typing.List` [:class:`~patcher.models.patch.PatchTitle`]
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
            raise  # Non 404 errors get re-raised

        labels = self._labels or await self.get_labels()
        label_lookup = {label.name.lower(): label for label in labels}

        matched_count = 0
        unmatched_apps = []

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

            matched_labels = self._match_directly(app_names, label_lookup) or self._match_fuzzy(
                app_names, label_lookup
            )

            if matched_labels:
                patch_title.install_label.extend(matched_labels)
                matched_count += 1
            else:
                unmatched_apps.append({"Patch": patch_title.title, "App Names": app_names})

        matched_count += self._second_pass(unmatched_apps, label_lookup, patch_titles)

        self._save_unmatched_apps(unmatched_apps)

        self.log.info(
            f"Matching process finished. {matched_count} PatchTitle objects were updated."
        )
        self.log.warning(
            f"{len(unmatched_apps)} PatchTitle objects had no matches. Review: {self.review_file}"
        )
