import json
from datetime import datetime
from typing import Dict, List, Optional

from ..models.patch import PatchTitle
from ..utils.decorators import check_token
from ..utils.exceptions import APIResponseError, PatcherError, ShellCommandError
from ..utils.logger import LogMe
from . import BaseAPIClient
from .config_manager import ConfigManager
from .token_manager import TokenManager


class ApiClient(BaseAPIClient):
    """
    Provides methods for interacting with the Jamf API, specifically fetching patch data, device information, and OS versions.

    All methods of the ApiClient class will raise an :exc:`~patcher.utils.exceptions.APIResponseError` if the API call is
    unsuccessful.

    .. seealso::
        :meth:`~patcher.client.__init__.BaseAPIClient.fetch_json`

    """

    def __init__(self, config: ConfigManager, concurrency: int):
        """
        Initializes the ApiClient with the provided :class:`~patcher.client.config_manager.ConfigManager`.

        This sets up the API client with necessary credentials and session parameters for interacting with the Jamf API.

        .. seealso::
            :class:`~patcher.models.jamf_client.JamfClient`

        :param config: Instance of ConfigManager for loading and storing credentials.
        :type config: ConfigManager
        """
        self.log = LogMe(self.__class__.__name__)
        self.config = config
        self.token_manager = TokenManager(config)  # Use for check_token decorator

        # Creds can be loaded here as ApiClient objects can only exist after successful JamfClient creation.
        self.jamf_client = config.attach_client()
        self.jamf_url = self.jamf_client.base_url

        super().__init__(max_concurrency=concurrency)

    def _convert_tz(self, utc_time_str: str) -> str:
        """
        Converts a UTC time string to a formatted string without timezone information.

        :param utc_time_str: UTC time string in ISO 8601 format (e.g., "2023-08-09T12:34:56+0000").
        :type utc_time_str: str
        :return: Formatted date string (e.g., "Aug 09 2023") or None if the input format is invalid.
        :rtype: str
        :raises PatcherError: If the time format provided is invalid.
        """
        try:
            utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S%z")
            return utc_time.strftime("%b %d %Y")
        except ValueError as e:
            self.log.error(f"Invalid time format provided. Details: {e}")
            raise PatcherError("Invalid time format provided.", time_str=utc_time_str) from e

    @check_token
    async def get_policies(self) -> List[str]:
        """
        Retrieves a list of patch software title IDs from the Jamf API.

        :return: A list of software title IDs or None if an error occurs.
        :rtype: List
        """
        url = f"{self.jamf_url}/api/v2/patch-software-title-configurations"
        response = await self.fetch_json(url=url, headers=self.jamf_client.headers)
        self.log.info("Patch policies obtained as expected.")
        return [title.get("id") for title in response]

    @check_token
    async def get_summaries(self, policy_ids: List[str]) -> List[PatchTitle]:
        """
        Retrieves patch summaries asynchronously for the specified policy IDs from the Jamf API.

        :param policy_ids: List of policy IDs to retrieve summaries for.
        :type policy_ids: List[str]
        :return: List of ``PatchTitle`` objects containing patch summaries.
        :rtype: List[:class:`~patcher.models.patch.PatchTitle`]
        """
        urls = [
            f"{self.jamf_url}/api/v2/patch-software-title-configurations/{policy}/patch-summary"
            for policy in policy_ids
        ]
        summaries = await self.fetch_batch(urls, headers=self.jamf_client.headers)

        patch_titles = [
            PatchTitle(
                title=summary.get("title"),
                released=self._convert_tz(summary.get("releaseDate")),
                hosts_patched=summary.get("upToDate"),
                missing_patch=summary.get("outOfDate"),
                latest_version=summary.get("latestVersion"),
            )
            for summary in summaries
            if summary
        ]
        self.log.info(f"Successfully obtained policy summaries for {len(patch_titles)} policies.")
        return patch_titles

    @check_token
    async def get_device_ids(self) -> Optional[List[int]]:
        """
        Asynchronously fetches the list of mobile device IDs from the Jamf Pro API.
        This method is only called if the :ref:`iOS <ios>` option is passed to the CLI.

        :return: A list of mobile device IDs or None on error.
        :rtype: Optional[List[int]]
        """
        url = f"{self.jamf_url}/api/v2/mobile-devices"
        response = await self.fetch_json(url=url, headers=self.jamf_client.headers)
        devices = response.get("results")
        self.log.info(f"Received {len(devices)} device IDs successfully.")
        return [device.get("id") for device in devices if device]

    @check_token
    async def get_device_os_versions(
        self,
        device_ids: List[int],
    ) -> Optional[List[Dict[str, str]]]:
        """
        Asynchronously fetches the OS version and serial number for each device ID provided.
        This method is only called if the :ref:`iOS <ios>` option is passed to the CLI.

        :param device_ids: A list of mobile device IDs to retrieve information for.
        :type device_ids: List[int]
        :return: A list of dictionaries containing the serial numbers and OS versions, or None on error.
        :rtype: Optional[List[Dict[str, str]]]
        """
        urls = [f"{self.jamf_url}/api/v2/mobile-devices/{device}/detail" for device in device_ids]
        subsets = await self.fetch_batch(urls, headers=self.jamf_client.headers)

        devices = [
            {
                "SN": subset.get("serialNumber"),
                "OS": subset.get("osVersion"),
            }
            for subset in subsets
            if subset
        ]
        self.log.info(f"Successfully obtained OS versions for {len(devices)} devices.")
        return devices

    async def get_sofa_feed(self) -> Optional[List[Dict[str, str]]]:
        """
        Fetches iOS Data feeds from SOFA and extracts latest OS version information.
        To limit the amount of possible SSL verification checks, this method utilizes a subprocess call
        instead.
        This method is only called if the :ref:`iOS <ios>` option is passed to the CLI.

        :return: A list of dictionaries containing base OS versions, latest iOS versions and release dates,
                or None on error.
        :rtype: Optional[List[Dict[str, str]]]
        :raises APIResponseError: If return code from SOFA command is non-zero.
        """
        # Call can be made directly as no additional headers or payloads need to be added
        command = ["/usr/bin/curl", "-s", "https://sofafeed.macadmins.io/v1/ios_data_feed.json"]

        try:
            result = await self.execute(command)
        except ShellCommandError as e:
            self.log.error(f"Error fetching data from SOFA feed. Details: {e}")
            raise APIResponseError("Unable to retrieve SOFA feed", command=command) from e

        # Convert to JSON for proper parsing
        result_json = json.loads(result)

        # Get OS version from response
        os_versions = result_json.get("OSVersions", [])

        # Iterate over versions to obtain iOS 16 & iOS 17 datasets
        latest_versions = []
        for version in os_versions:
            version_info = version.get("Latest", {})
            latest_versions.append(
                {
                    "OSVersion": version.get("OSVersion"),
                    "ProductVersion": version_info.get("ProductVersion"),
                    "ReleaseDate": self._convert_tz(version_info.get("ReleaseDate")),
                }
            )
        return latest_versions
