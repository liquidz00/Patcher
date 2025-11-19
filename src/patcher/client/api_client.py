import json
from datetime import datetime
from typing import Any, AsyncGenerator

from ..models.patch import PatchDevice, PatchTitle
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
        :type concurrency: int
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
            raise PatcherError(
                "Invalid time format provided.",
                time_str=utc_time_str,
                error_msg=str(e),
            )

    async def _headers(self) -> dict[str, str]:
        """Generates headers for API calls, ensuring the latest token is used."""
        # Ensure token is valid
        await self.token_manager.ensure_valid_token()
        latest_token = self.token_manager.token
        self.log.debug(f"Using token ending in {latest_token.token[-4:]}")
        return {"accept": "application/json", "Authorization": f"Bearer {latest_token}"}

    @check_token
    async def get_policies(self) -> list[str]:
        """
        Retrieves a list of patch software title IDs from the Jamf API.

        :return: A list of software title IDs.
        :rtype: list[str]
        """
        headers = await self._headers()
        url = f"{self.jamf_url}/api/v2/patch-software-title-configurations"
        try:
            response = await self.fetch_json(url=url, headers=headers)
        except APIResponseError:
            raise
        return [title.get("id") for title in response]

    @check_token
    async def get_summaries(self, policy_ids: list[str]) -> list[PatchTitle]:
        """
        Retrieves patch summaries asynchronously for the specified policy IDs from the Jamf API.

        :param policy_ids: list of policy IDs to retrieve summaries for.
        :type policy_ids: list[str]
        :return: list of ``PatchTitle`` objects containing patch summaries.
        :rtype: list[:class:`~patcher.models.patch.PatchTitle`]
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

    async def stream_title_report(
        self, title_id: str, page_size: int = 100
    ) -> AsyncGenerator[list[PatchDevice], None]:
        """
        Stream patch report data for a specific software title in batches.

        This method yields batches of devices as they are fetched, allowing for
        memory-efficient processing and progress tracking. Each batch corresponds
        to one API page response.

        :param title_id: The software title ID to retrieve the patch report for.
        :type title_id: str
        :param page_size: Number of devices to fetch per page. Defaults to 100.
        :type page_size: int
        :yields: Batches of ``PatchDevice`` objects.
        :rtype: AsyncGenerator[list[:class:`~patcher.models.patch.PatchDevice`], None]
        """
        headers = await self._headers()
        base_url = (
            f"{self.jamf_url}/api/v2/patch-software-title-configurations/{title_id}/patch-report"
        )

        page = 0
        total_fetched = 0
        total_count = None

        while True:
            query_params = {
                "page": page,
                "page-size": page_size,
            }

            try:
                response = await self.fetch_json(
                    url=base_url, headers=headers, query_params=query_params
                )
            except APIResponseError:
                raise

            page_results = response.get("results", [])
            if total_count is None:
                total_count = response.get("totalCount", 0)
                self.log.info(f"Title {title_id} installed on {total_count} total devices")

            if not page_results:
                self.log.debug(f"No more results at page {page} for title {title_id}")
                break

            page_devices = [PatchDevice(**d) for d in page_results]
            total_fetched += len(page_devices)

            self.log.debug(
                f"Fetched page {page} ({len(page_devices)} devices) for title {title_id}"
            )
            yield page_devices

            if total_fetched >= total_count:
                self.log.debug(f"Reached total count for title {title_id}")
                break

            page += 1

    @check_token
    async def get_title_report(self, title_id: str, page_size: int = 100) -> list[PatchDevice]:
        """
        Retrieve the complete patch report for a specific software title.

        This method collects all device records across all pages and returns them
        as a single list. Best suited for Excel/PDF exports where all data is needed
        upfront.

        :param title_id: The software title ID to retrieve the patch report for.
        :type title_id: str
        :param page_size: Number of devices to fetch per page. Defaults to 100.
        :type page_size: int
        :return: List of all PatchDevice objects for the title.
        :rtype: list[:class:`~patcher.models.patch.PatchDevice`]
        """
        devices = []
        async for batch in self.stream_title_report(title_id, page_size=page_size):
            devices.extend(batch)

        self.log.info(f"Collected {len(devices)} total devices for title {title_id}")
        return devices

    @check_token
    async def get_title_reports(
        self, title_ids: list[str], page_size: int = 100
    ) -> dict[str, list[PatchDevice]]:
        """
        Retrieves patch reports for multiple software titles.

        Processes titles sequentially to avoid overwhelming the Jamf API. Each title's
        pagination is handled by the underlying stream/fetch methods.

        :param title_ids: List of software title IDs to retrieve reports for.
        :type title_ids: list[str]
        :param page_size: Number of devices to fetch per page. Defaults to 100.
        :type page_size: int
        :return: Dictionary mapping title IDs to lists of PatchDevice objects.
        :rtype: dict[str, list[:class:`~patcher.models.patch.PatchDevice`]]
        """
        self.log.debug(f"Fetching patch reports for {len(title_ids)} titles")
        results = {}

        for title_id in title_ids:
            self.log.info(f"Processing patch report for title {title_id}")

            try:
                title_devices = await self.get_title_report(title_id, page_size=page_size)
                results[title_id] = title_devices
            except APIResponseError as e:
                self.log.error(f"Failed to fetch report for title {title_id}: {e}")
                results[title_id] = []

        total_devices = sum(len(devices) for devices in results.values())
        self.log.info(f"Collected {total_devices} total devices across {len(title_ids)} titles")
        return results

    @check_token
    async def get_device_ids(self) -> list[int]:
        """
        Asynchronously fetches the list of mobile device IDs from the Jamf Pro API.

        .. note::
            This method is only called if the :ref:`iOS <ios>` option is passed to the CLI.

        :return: A list of mobile device IDs.
        :rtype: list[int]
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
    async def get_device_os_versions(self, device_ids: list[int]) -> list[dict[str, str]]:
        """
        Asynchronously fetches the OS version and serial number for each device ID provided.

        .. note::
            This method is only called if the :ref:`iOS <ios>` option is passed to the CLI.

        :param device_ids: A list of mobile device IDs to retrieve information for.
        :type device_ids: list[int]
        :return: A list of dictionaries containing the serial numbers and OS versions.
        :rtype: list[dict[str, str]]
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
    async def get_app_names(self, patch_titles: list[PatchTitle]) -> list[dict[str, Any]]:
        """
        Fetches all possible app names for each ``PatchTitle`` object provided.

        :param patch_titles: list of ``PatchTitle`` objects.
        :type patch_titles: list[:class:`~patcher.models.patch.PatchTitle`]
        :return: list of dictionaries containing the ``PatchTitle`` title and corresponding ``appName``
        :rtype: list[dict[str, Any]]
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

    async def get_sofa_feed(self) -> list[dict[str, str]]:
        """
        Fetches iOS Data feeds from SOFA and extracts latest OS version information.

        To limit the amount of possible SSL verification checks, this method utilizes a subprocess call instead.

        .. note::
            This method is only called if the :ref:`iOS <ios>` option is passed to the CLI.

        :return: A list of dictionaries containing base OS versions, latest iOS versions, and release dates.
        :rtype: list[dict[str, str]]
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
