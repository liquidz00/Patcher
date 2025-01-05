import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..client import BaseAPIClient
from ..models.label import Label
from .exceptions import PatcherError, ShellCommandError
from .logger import LogMe


class Installomator:
    def __init__(self):
        self.log = LogMe(self.__class__.__name__)
        self.label_path = Path.home() / "Library" / "Application Support" / "Patcher" / ".labels"
        self.installomator_url = (
            "https://api.github.com/repos/Installomator/Installomator/contents/fragments/labels"
        )
        self.api = BaseAPIClient()

    async def _save(self, file_name: str, download_url: str, file_path: Path) -> bool:
        try:
            file_content = await self.api.execute(["/usr/bin/curl", "-s", download_url])
        except ShellCommandError as e:
            self.log.error(f"Unable to download Installomator fragment as expected. Details: {e}")
            raise

        try:
            with open(file_path, "w") as f:
                f.write(file_content)
            self.log.debug(f"Downloaded and saved {file_name}")
            return True
        except OSError as e:
            self.log.error(f"Could not write to {file_path}: {e}")
            raise PatcherError(
                "Could not write to provided file path due to OSError.", path=file_path
            ) from e

    @staticmethod
    def _parse(fragment: str) -> Dict[str, Any]:
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

    async def fetch_fragments(self) -> Optional[List[Dict]]:
        response = await self.api.execute(["/usr/bin/curl", "-s", self.installomator_url])
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            self.log.error(f"Installomator fragment response could not be decoded: {e}")
            raise PatcherError("Encountered JSON error when decoding Installomator fragment") from e

    async def create_labels(self) -> List[Label]:
        labels = []

        for file_path in self.label_path.glob("*.sh"):
            content = await asyncio.to_thread(file_path.read_text)
            fragment_dict = self._parse(content)
            try:
                label = Label.from_dict(fragment_dict, installomatorLabel=file_path.stem)
                labels.append(label)
            except ValueError as e:
                self.log.error(
                    f"Failed to create Label from fragment {file_path.name}. Details: {e}"
                )
                raise PatcherError(
                    "Could not create Label object from fragment", fragment=file_path.stem
                ) from e

        return labels

    async def create_label_dir(self, fragments: List[Dict[str, Any]]) -> bool:
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
