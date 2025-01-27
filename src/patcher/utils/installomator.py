import json
import re
from typing import Any, Dict, List, Optional

from ..client.api_client import ApiClient
from ..client.config_manager import ConfigManager
from ..models.fragment import Fragment
from ..models.label import Label
from .data_manager import DataManager
from .exceptions import PatcherError, ShellCommandError
from .logger import LogMe


class Installomator:
    def __init__(self, max_concurrency: Optional[int] = 5):
        """
        # TODO

        :param max_concurrency:
        :type max_concurrency:
        """
        self.log = LogMe(self.__class__.__name__)
        self.config = ConfigManager()
        self.api = ApiClient(config=self.config, concurrency=max_concurrency)
        self.data_manager = DataManager()

        self._labels: Optional[List[Label]] = None
        self._fragments: Optional[List[Fragment]] = None

    @property
    def labels(self) -> List[Label]:
        """
        Returns the current list of ``Label`` objects gathered from Installomator API calls.

        :return: The current list of ``Label`` objects.
        :rtype: :py:obj:`~typing.List` [:class:`~patcher.models.label.Label`]
        """
        if self._labels is None:
            self._labels = self._build_labels()
        return self._labels

    @labels.setter
    def labels(self, value: List[Label]):
        """
        Sets the labels property after validation.

        :param value: A list of ``Label`` objects to assign.
        :type value: :py:obj:`~typing.List` [:class:`~patcher.models.label.Label`]
        """
        self._labels = self._validate_labels(value)

    @property
    def fragments(self) -> List[Fragment]:
        """
        # TODO

        :return:
        :rtype: :py:obj:`~typing.List` [:class:`~patcher.models.fragment.Fragment`]
        """
        if self._fragments is None:
            self._fragments = self._fetch_fragments()
        return self._fragments

    @staticmethod
    def _validate_labels(value: List[Any]) -> List[Label]:
        """Validates the provided value is a list of ``Label`` objects."""
        if not isinstance(value, list):
            raise PatcherError("Value provided is not a list of Label objects.", value=value)

        validated_labels = [item for item in value if isinstance(item, Label)]
        if not validated_labels:
            raise PatcherError("List provided does not contain any valid Label objects.")

        return validated_labels

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
                data[key] = [val[0] or val[1] for val in data[key]]  # Flatten matches
                continue

            # Match key-value pairs
            kv_match = kv_pattern.match(line)
            if kv_match:
                key, value = kv_match.groups()
                # Strip surrounding quotes for quoted values
                value = value.strip('"')
                data[key] = value  # type: ignore
                continue

        return data

    def _fetch_fragments(self) -> List[Fragment]:
        """Fetches Installomator fragments via GitHub API."""
        installomator_url = (
            "https://api.github.com/repos/Installomator/Installomator/contents/fragments/labels"
        )
        command = ["/usr/bin/curl", "-s", installomator_url]
        try:
            bytes_response = self.api.execute_sync(command)
            response = json.loads(bytes_response)
            return [Fragment(**item) for item in response]
        except (ShellCommandError, json.JSONDecodeError, ValueError) as e:
            raise PatcherError(
                "Unable to retrieve Installomator fragments as expected.", error_msg=str(e)
            )

    def _build_labels(self) -> List[Label]:
        """Constructs ``Label`` objects from retrieved fragments."""
        labels = []
        # Fetch fragments
        fragments = self._fetch_fragments()
        for fragment in fragments:
            try:
                command = ["/usr/bin/curl", "-s", "-X", "GET", fragment.download_url]
                label_str = self.api.execute_sync(command).decode()
                label_dict = self._parse(label_str)
                label = Label.from_dict(
                    data=label_dict, installomatorLabel=(fragment.name.split(".")[0])
                )
                labels.append(label)
            except (ShellCommandError, PatcherError, ValueError) as e:
                self.log.warning(f"Failed to process fragment '{fragment.name}'. Details: {e}")
                break  # Skip to next fragment

        return labels

    async def match(self):
        """
        # TODO

        :return:
        :rtype:
        """
        # Retrieve patch title / app name dict from api
        software_titles = await self.api.get_app_names(patch_titles=self.data_manager.titles)

        # Parse label objects for app name
        # Add Label.installomatorLabel (or entire Label object?) to PatchTitle.install_label list if match found
        # Handle multiple matches (PatchTitle.install_label accepts List of ``Label`` objects)
