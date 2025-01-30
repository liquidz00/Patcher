import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..client.api_client import ApiClient
from ..client.config_manager import ConfigManager
from ..models.fragment import Fragment
from ..models.label import Label
from .data_manager import DataManager
from .exceptions import APIResponseError, PatcherError, ShellCommandError
from .logger import LogMe


class Installomator:
    def __init__(self, max_concurrency: Optional[int] = 5):
        """
        # TODO

        :param max_concurrency:
        :type max_concurrency:
        """
        self.log = LogMe(self.__class__.__name__)
        self.label_path = Path.home() / "Library/Application Support/Patcher/.labels"
        self.config = ConfigManager()
        self.api = ApiClient(config=self.config, concurrency=max_concurrency)
        self.data_manager = DataManager()

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
            try:
                label = Label.from_dict(
                    fragment_dict, installomatorLabel=file_path.stem.split(".")[0]
                )
                labels.append(label)
            except ValueError as e:
                raise PatcherError(
                    "Failed to create Label object from fragment.",
                    fragment=file_path.name,
                    error_msg=str(e),
                )

        # Cache labels
        self._labels = labels

        return labels

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

    async def match(self):
        """
        # TODO
        #   - Identify if API client should return list of Dicts for get_app_names or single Dict
        #   - Match method logic will need to change depending on that
        #   - Currently `get_app_names` returns single Dict, `match` will fail as its configured to work with a list

        :return:
        :rtype:
        """
        self.log.debug("Starting label-patch title matching process.")

        # Retrieve patch title / app name dict from api
        software_titles = await self.api.get_app_names(patch_titles=self.data_manager.titles)

        # Parse label objects for app name
        labels = self._labels or await self.get_labels()

        label_lookup = {label.name.lower(): label for label in labels}
        matched_count = 0  # Track number of PatchTitle objects with matched labels

        for patch_title in self.data_manager.titles:
            app_name = software_titles.get("App Name").lower().strip()

            if not app_name:
                self.log.warning(f"Skipping {patch_title.title} - No app name found.")
                continue

            # Handle multiple matches
            matched_labels = [
                label for label_name, label in label_lookup.items() if app_name in label_name
            ]

            # Add Label to PatchTitle.install_label list if match found
            if matched_labels:
                patch_title.install_label.extend(matched_labels)
                matched_count += 1

        self.log.info(
            f"Matching process finished. {matched_count} PatchTitle objects were updated."
        )
