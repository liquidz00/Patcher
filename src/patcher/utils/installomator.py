import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..client import BaseAPIClient
from ..models.label import Label
from .exceptions import APIResponseError, PatcherError, ShellCommandError
from .logger import LogMe


class Installomator:
    def __init__(self):
        self.log = LogMe(self.__class__.__name__)
        self.label_path = Path.home() / "Library/Application Support/Patcher/.labels"
        self.installomator_url = (
            "https://api.github.com/repos/Installomator/Installomator/contents/fragments/labels"
        )
        self.api = BaseAPIClient()

        self._labels: Optional[List[Label]] = None  # Lazy load labels

    @property
    def labels(self) -> List[Label]:
        return self._labels if self._labels else []

    @labels.setter
    def labels(self, value: List[Label]):
        if not isinstance(value, list):
            raise PatcherError("Value provided is not a list of Label objects.", value=value)

        validated_labels = [item for item in value if isinstance(item, Label)]
        if not validated_labels:
            raise PatcherError("List provided does not contain any valid Label objects.")

        self._labels = validated_labels

    async def _save(self, file_name: str, download_url: str, file_path: Path) -> bool:
        """Saves Installomator fragments to specified file path."""
        self.log.debug(f"Attempting to download Installomator fragments to {file_path}.")
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
        fragment = re.sub(r"^\w+\n", "", fragment).strip()
        fragment = re.sub(r";;\s*$", "", fragment).strip()

        data = {}
        pattern = r'(\w+)=(".*?"|\$\(.*?\)|[^\s]+)'
        matches = re.findall(pattern, fragment)

        for key, value in matches:
            value = value.strip('"')
            if value.startswith("$(") and value.endswith(")"):
                value = value

            data[key] = value

        return data

    async def _fetch_fragments(self) -> List[Dict]:
        """Fetches Installomator fragments via GitHub API."""
        try:
            return await self.api.fetch_json(self.installomator_url)  # type: ignore
        except APIResponseError as e:
            self.log.error(
                f"Unable to retrieve Installomator fragments via API call as expected. Details: {e}"
            )
            raise PatcherError(
                "Unable to retrieve Installomator fragments as expected.", error_msg=str(e)
            )

    def _create_labels(self) -> List[Label]:
        """Creates ``Label`` objects from saved Installomator fragments."""
        labels = []

        for file_path in self.label_path.glob("*.sh"):
            content = file_path.read_text()
            fragment_dict = self._parse(content)
            try:
                label = Label.from_dict(fragment_dict, installomatorLabel=file_path.stem)
                labels.append(label)
            except ValueError as e:
                self.log.error(
                    f"Failed to create Label from fragment {file_path.name}. Details: {e}"
                )
                raise PatcherError(
                    "Could not create Label object from fragment",
                    fragment=file_path.stem,
                    error_msg=str(e),
                )

        return labels

    async def _create_label_dir(self, fragments: List[Dict[str, Any]]) -> bool:
        """Creates label directory to ensure Installomator fragments are saved locally."""
        # Ensure self.label_path exists
        if not self.label_path.exists():
            self.label_path.mkdir(parents=True, exist_ok=True)

        tasks = []
        for fragment in fragments:
            if fragment["type"] == "file" and fragment.get("download_url"):
                fragment_name = fragment["name"]
                save_path = self.label_path / fragment_name

                if not save_path.exists():
                    tasks.append(
                        self._save(
                            file_name=fragment_name,
                            download_url=fragment["download_url"],
                            file_path=save_path,
                        )
                    )

        results = await asyncio.gather(*tasks)
        return all(result is True for result in results)

    async def initialize(self):
        # Fetch fragments
        fragments = await self._fetch_fragments()

        # Create label directory
        if not await self._create_label_dir(fragments):
            self.log.error("Failed to create label directory as expected.")
            raise PatcherError(
                "Encountered error during Installomator setup trying to create label directory.",
                path=self.label_path,
            )

        # Populate Label objects and cache them
        self.labels = self._create_labels()
