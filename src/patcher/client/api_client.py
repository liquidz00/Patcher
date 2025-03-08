import json
from datetime import datetime
from typing import Any, Dict, List

from ..models.patch import PatchTitle
from ..utils.decorators import check_token
from ..utils.exceptions import APIResponseError, PatcherError, ShellCommandError
from ..utils.logger import LogMe
from . import BaseAPIClient
from .config_manager import ConfigManager
from .token_manager import TokenManager


class ApiClient(BaseAPIClient):
    def __init__(self, config: ConfigManager, concurrency: int):
        """
        Provides methods for interacting with the Jamf API, specifically fetching patch data, device information, and OS versions.

        .. note::
            All methods of the ApiClient class will raise an :exc:`~patcher.utils.exceptions.APIResponseError` if the API call is unsuccessful.

        :param config: Instance of ``ConfigManager`` for loading and storing credentials.
        :type config: :class:`~patcher.client.config_manager.ConfigManager`
        :param concurrency: Maximum number of concurrent API requests. See :ref:`concurrency <concurrency>` in Usage docs.
        :type concurrency: :py:class:`int`
        """
        self.log = LogMe(self.__class__.__name__)
        self.config = config
        self.token_manager = TokenManager(config)

        # Creds can be loaded here as ApiClient objects can only exist after successful JamfClient creation.
        self.jamf_client = self.token_manager.attach_client()
        self.jamf_url = self.jamf_client.base_url

        super().__init__(max_concurrency=concurrency)

    def _convert_tz(self, utc_time_str: str) -> str:
        """
        Converts a UTC time string to a formatted string without timezone information.

        :param utc_time_str: UTC time string in ISO 8601 format (e.g., "2023-08-09T12:34:56+0000").
        :type utc_time_str: :py:class:`str`
        :return: Formatted date string (e.g., "Aug 09 2023") or None if the input format is invalid.
        :rtype: :py:class:`str`
        :raises PatcherError: If the time format provided is invalid.
        """
        try:
            utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S%z")
            return utc_time.strftime("%b %d %Y")
        except ValueError as e:
            self.log.error(f"Invalid time format provided. Details: {e}")
            raise PatcherError(
                "Invalid time format provided.",
                time_str=utc_time_str,
                error_msg=str(e),
            )

    async def _headers(self) -> Dict[str, str]:
        """Generates headers for API calls, ensuring the latest token is used."""
        # Ensure token is valid
        await self.token_manager.ensure_valid_token()
        latest_token = self.token_manager.token
        self.log.debug(f"Using token ending in {latest_token.token[-4:]}")
        return {"accept": "application/json", "Authorization": f"Bearer {latest_token}"}

    @check_token
    async def get_policies(self) -> List[str]:
        """
        Retrieves a list of patch software title IDs from the Jamf API.

        :return: A list of software title IDs.
        :rtype: :py:obj:`~typing.List` [:py:class:`str`]
        """
        headers = await self._headers()
        url = f"{self.jamf_url}/api/v2/patch-software-title-configurations"
        try:
            response = await self.fetch_json(url=url, headers=headers)
        except APIResponseError:
            raise
        return [title.get("id") for title in response]

    @check_token
    async def get_summaries(self, policy_ids: List[str]) -> List[PatchTitle]:
        """
        Retrieves patch summaries asynchronously for the specified policy IDs from the Jamf API.

        :param policy_ids: List of policy IDs to retrieve summaries for.
        :type policy_ids: :py:obj:`~typing.List` [:py:class:`str`]
        :return: List of ``PatchTitle`` objects containing patch summaries.
        :rtype: :py:obj:`~typing.List` [:class:`~patcher.models.patch.PatchTitle`]
        """
        urls = [
            f"{self.jamf_url}/api/v2/patch-software-title-configurations/{policy}/patch-summary"
            for policy in policy_ids
        ]
        headers = await self._headers()
        try:
            summaries = await self.fetch_batch(urls, headers=headers)
        except APIResponseError:
            raise

        patch_titles = [
            PatchTitle(
                title=summary.get("title"),
                title_id=summary.get("softwareTitleId"),
                released=self._convert_tz(summary.get("releaseDate")),
                hosts_patched=summary.get("upToDate"),
                missing_patch=summary.get("outOfDate"),
                latest_version=summary.get("latestVersion"),
            )
            for summary in summaries
            if summary
        ]
        return patch_titles

    @check_token
    async def get_device_ids(self) -> List[int]:
        """
        Asynchronously fetches the list of mobile device IDs from the Jamf Pro API.

        .. note::
            This method is only called if the :ref:`iOS <ios>` option is passed to the CLI.

        :return: A list of mobile device IDs.
        :rtype: :py:obj:`~typing.List` [:py:class:`int`]
        """
        url = f"{self.jamf_url}/api/v2/mobile-devices"
        headers = await self._headers()
        try:
            response = await self.fetch_json(url=url, headers=headers)
        except APIResponseError:
            raise
        devices = response.get("results")
        return [device.get("id") for device in devices if device]

    @check_token
    async def get_device_os_versions(self, device_ids: List[int]) -> List[Dict[str, str]]:
        """
        Asynchronously fetches the OS version and serial number for each device ID provided.

        .. note::
            This method is only called if the :ref:`iOS <ios>` option is passed to the CLI.

        :param device_ids: A list of mobile device IDs to retrieve information for.
        :type device_ids: :py:obj:`~typing.List` [:py:class:`int`]
        :return: A list of dictionaries containing the serial numbers and OS versions.
        :rtype: :py:obj:`~typing.List` [:py:obj:`~typing.Dict`]
        """
        urls = [f"{self.jamf_url}/api/v2/mobile-devices/{device}/detail" for device in device_ids]
        headers = await self._headers()
        try:
            subsets = await self.fetch_batch(urls, headers=headers)
        except APIResponseError:
            raise

        devices = [
            {
                "SN": subset.get("serialNumber"),
                "OS": subset.get("osVersion"),
            }
            for subset in subsets
            if subset
        ]
        return devices

    @check_token
    async def get_app_names(self, patch_titles: List[PatchTitle]) -> List[Dict[str, Any]]:
        """
        Fetches all possible app names for each ``PatchTitle`` object provided.

        :param patch_titles: List of ``PatchTitle`` objects.
        :type patch_titles: :py:obj:`~typing.List` [:class:`~patcher.models.patch.PatchTitle`]
        :return: List of dictionaries containing the ``PatchTitle`` title and corresponding ``appName``
        :rtype: :py:obj:`~typing.List` [:py:obj:`~typing.Dict`]
        """
        title_ids = [patch.title_id for patch in patch_titles if patch.title_id != "iOS"]
        urls = [
            f"{self.jamf_url}/api/v2/patch-software-title-configurations/{title_id}/definitions"
            for title_id in title_ids
        ]
        query_params = {"page-size": 1, "sort": "absoluteOrderId:asc"}
        headers = await self._headers()
        try:
            batch_responses = await self.fetch_batch(
                urls, headers=headers, query_params=query_params
            )
        except APIResponseError as e:
            if getattr(e, "not_found", False):
                return []
            raise

        app_names = []
        for patch_title, response in zip(patch_titles, batch_responses):
            results = response.get("results")
            extracted_app_names = []

            if results:
                kill_apps = results[0].get("killApps")
                extracted_app_names = [
                    app.get("appName") for app in kill_apps if app.get("appName")
                ]

            app_names.append(
                {
                    "Patch": patch_title.title,
                    "App Names": extracted_app_names,
                }
            )

        return app_names

    async def get_sofa_feed(self) -> List[Dict[str, str]]:
        """
        Fetches iOS Data feeds from SOFA and extracts latest OS version information.

        To limit the amount of possible SSL verification checks, this method utilizes a subprocess call instead.

        .. note::
            This method is only called if the :ref:`iOS <ios>` option is passed to the CLI.

        :return: A list of dictionaries containing base OS versions, latest iOS versions, and release dates.
        :rtype: :py:obj:`~typing.List` [:py:obj:`~typing.Dict`]
        :raises APIResponseError: If return code from SOFA is non-zero.
        """
        # Call can be made directly as no additional headers or payloads need to be added
        command = ["/usr/bin/curl", "-s", "https://sofafeed.macadmins.io/v1/ios_data_feed.json"]

        try:
            result = await self.execute(command)
        except ShellCommandError as e:
            raise APIResponseError(
                "Unable to retrieve SOFA feed",
                command=command,
                error_msg=str(e),
            )

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
