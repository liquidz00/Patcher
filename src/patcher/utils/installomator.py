import asyncio
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.label import Label
from .exceptions import InstallomatorError
from .logger import LogMe


class Installomator:
    def __init__(self):
        self.log = LogMe(self.__class__.__name__)
        self.label_path = Path.home() / "Library" / "Application Support" / "Patcher" / ".labels"
        self.installomator_url = (
            "https://api.github.com/repos/Installomator/Installomator/contents/fragments/labels"
        )

    async def _save(self, file_name: str, download_url: str, file_path: Path) -> bool:
        file_content = await self._fetch(["/usr/bin/curl", "-s", download_url])

        try:
            with open(file_path, "w") as f:
                f.write(file_content)
            self.log.debug(f"Downloaded and saved {file_name}")
            return True
        except OSError as e:
            self.log.error(f"Could not write to {file_path}: {e}")
            raise

    async def _fetch(self, command: List[str]) -> str:
        process = await asyncio.create_subprocess_exec(
            *command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            self.log.error(f"curl failed with error: {stderr.decode()}")
        return stdout.decode()

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
        response = await self._fetch(["/usr/bin/curl", "-s", self.installomator_url])
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            self.log.error(f"Installomator fragment response could not be decoded: {e}")
            raise InstallomatorError(f"Installomator fragment response could not be decoded: {e}")

    async def create_labels(self) -> List[Label]:
        labels = []

        for file_path in self.label_path.glob("*.sh"):
            content = await asyncio.to_thread(file_path.read_text)
            fragment_dict = self._parse(content)
            try:
                label = Label.from_dict(fragment_dict, installomatorLabel=file_path.stem)
                labels.append(label)
            except ValueError as e:
                self.log.error(f"Failed to create Label from fragment {file_path.name}: {e}")

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
