import aiohttp
import asyncio
import subprocess
import json
from datetime import datetime
from typing import AnyStr, Optional, Dict, List
from src.Patcher import logger
from src.Patcher.client.token_manager import TokenManager
from src.Patcher.client.config_manager import ConfigManager
from src.Patcher.wrappers import check_token

logthis = logger.setup_child_logger("ApiClient", __name__)


class ApiClient:
    """Provides methods for interacting with the Jamf API."""

    def __init__(self, config: ConfigManager):
        """
        Initializes the ApiClient with the provided ConfigManager.

        :param config: Instance of ConfigManager for loading and storing credentials.
        :type config: ConfigManager
        :raises ValueError: If the JamfClient configuration is invalid.
        """
        self.log = logthis
        self.config = config
        self.jamf_client = config.attach_client()
        if self.jamf_client:
            self.token = self.jamf_client.token
            self.log.info("JamfClient and token successfully attached")
        else:
            self.log.error("Invalid JamfClient configuration detected!")
            raise ValueError("Invalid JamfClient configuration detected!")
        self.jamf_url = self.jamf_client.base_url
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        self.token_manager = TokenManager(config)
        self.max_concurrency = self.jamf_client.max_concurrency
        self.log.debug("Initializing ApiClient")
        # self.connector = aiohttp.TCPConnector(limit=self.jamf_client.max_concurrency)

    @staticmethod
    def convert_timezone(utc_time_str: AnyStr) -> Optional[AnyStr]:
        """
        Converts a UTC time string to a formatted string without timezone information.

        :param utc_time_str: UTC time string in ISO 8601 format.
        :type utc_time_str: AnyStr
        :return: Formatted time string or error message.
        :rtype: AnyStr
        """
        try:
            utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S%z")
            time_str = utc_time.strftime("%b %d %Y")
            return time_str
        except ValueError as e:
            logthis.error(f"Invalid time format provided. Details: {e}")
            return None

    async def fetch_json(
        self, url: AnyStr, session: aiohttp.ClientSession
    ) -> Optional[Dict]:
        """
        Asynchronously fetches JSON data from a specified URL using a session.

        :param url: URL to fetch the JSON data from.
        :type url: AnyStr
        :param session: Async session used to make the request, instance of aiohttp.ClientSession.
        :type session: aiohttp.ClientSession
        :return: JSON data as a dictionary or an empty dictionary on error.
        :rtype: Optional[Dict]
        """
        logthis.debug(f"Fetching JSON data from URL: {url}")
        try:
            async with session.get(url, headers=self.headers) as response:
                response.raise_for_status()
                json_data = await response.json()
                self.log.info(f"Successfully fetched JSON data from {url}")
                return json_data
        except aiohttp.ClientResponseError as e:
            self.log.error(
                f"Received a client error while fetching JSON from {url}: {e}"
            )
        except Exception as e:
            self.log.error(f"Error fetching JSON: {e}")
        return None

    async def fetch_batch(self, urls: List[AnyStr]) -> List[Optional[Dict]]:
        """
        Fetches JSON data in batches to respect the concurrency limit. Data is fetched
        from each URL in the provided list, ensuring that no more than `max_concurrency`
        requests are sent concurrently.

        :param urls: A list of URLs to fetch JSON data from
        :type urls: List[AnyStr]
        :return: A list of dictionaries containing the JSON data fetched from each URL,
            or None on error.
        :rtype: List[Optional[Dict]]
        """
        results = []
        async with aiohttp.ClientSession() as session:
            for i in range(0, len(urls), self.max_concurrency):
                batch = urls[i: i + self.max_concurrency]
                tasks = [self.fetch_json(url, session) for url in batch]
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)
        return results

    @check_token
    async def get_policies(self) -> Optional[List]:
        """
        Asynchronously retrieves all patch software titles' IDs using the Jamf API.

        :return: List of software title IDs or None on error.
        :rtype: Optional[List]
        """
        async with aiohttp.ClientSession() as session:
            url = f"{self.jamf_url}/api/v2/patch-software-title-configurations"
            response = await self.fetch_json(url=url, session=session)

            # Verify response is list type as expected
            if not isinstance(response, list):
                self.log.error(
                    f"Unexpected response format: expected a list, received {type(response)} instead."
                )
                return None

            # Check if all elements in the list are dictionaries
            if not all(isinstance(item, dict) for item in response):
                self.log.error(
                    "Unexpected response format: all items should be dictionaries."
                )
                return None

            self.log.info("Patch policies obtained as expected.")
            return [title.get("id") for title in response]

    @check_token
    async def get_summaries(self, policy_ids: List) -> Optional[List]:
        """
        Retrieves active patch summaries for given policy IDs using the Jamf API.

        :param policy_ids: List of policy IDs to retrieve summaries for.
        :type policy_ids: List
        :return: List of dictionaries containing patch summaries or None on error.
        :rtype: Optional[List]
        """
        urls = [
            f"{self.jamf_url}/api/v2/patch-software-title-configurations/{policy}/patch-summary"
            for policy in policy_ids
        ]
        summaries = await self.fetch_batch(urls)

        policy_summaries = [
            {
                "software_title": summary.get("title"),
                "patch_released": self.convert_timezone(summary.get("releaseDate")),
                "hosts_patched": summary.get("upToDate"),
                "missing_patch": summary.get("outOfDate"),
                "completion_percent": (
                    round(
                        (
                            summary.get("upToDate")
                            / (summary.get("upToDate") + summary.get("outOfDate"))
                        )
                        * 100,
                        2,
                    )
                    if summary.get("upToDate") + summary.get("outOfDate") > 0
                    else 0
                ),
                "total_hosts": summary.get("upToDate") + summary.get("outOfDate"),
            }
            for summary in summaries
            if summary
        ]
        self.log.info(
            f"Successfully obtained policy summaries for {len(policy_summaries)} policies."
        )
        return policy_summaries

    @check_token
    async def get_device_ids(self) -> Optional[List[int]]:
        """
        Asynchronously fetches the list of mobile device IDs from the Jamf Pro API.

        :return: A list of mobile device IDs or None on error.
        :rtype: Optional[List[int]]
        """
        url = f"{self.jamf_url}/api/v2/mobile-devices"

        try:
            async with aiohttp.ClientSession() as session:
                response = await self.fetch_json(url=url, session=session)
        except aiohttp.ClientError as e:
            self.log.error(f"Error fetching device IDs: {e}")
            return None

        if not response:
            self.log.error(f"API call to {url} was unsuccessful.")
            return None

        devices = response.get("results")

        if not devices:
            self.log.error("Received empty data set when trying to obtain device IDs.")
            return None

        self.log.info(f"Received {len(devices)} device IDs successfully.")
        return [device.get("id") for device in devices if device]

    @check_token
    async def get_device_os_versions(
        self,
        device_ids: List[int],
    ) -> Optional[List[Dict[AnyStr, AnyStr]]]:
        """
        Asynchronously fetches the OS version and serial number for each device ID from the Jamf Pro API.

        :param device_ids: A list of mobile device IDs.
        :type device_ids: List[int]
        :return: A list of dictionaries containing the serial number and OS version, or None on error.
        :rtype: Optional[List[Dict[AnyStr, AnyStr]]]
        """
        if not device_ids:
            self.log.error("No device IDs provided!")
            return None
        urls = [
            f"{self.jamf_url}/api/v2/mobile-devices/{device}/detail"
            for device in device_ids
        ]
        subsets = await self.fetch_batch(urls)

        if not subsets:
            self.log.error("Received empty response obtaining device OS information.")
            return None

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

    def get_sofa_feed(self) -> Optional[List[Dict[AnyStr, AnyStr]]]:
        """
        Fetches iOS Data feeds from SOFA and extracts latest OS version information

        :return: A list of dictionaries containing Base OS Version, latest iOS Version and release date,
            or None on error.
        :rtype: Optional[List[Dict[AnyStr, AnyStr]]]
        """

        # Utilize curl to avoid SSL Verification errors for end-users on managed devices
        command = "curl -s 'https://sofa.macadmins.io/v1/ios_data_feed.json'"

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, check=True
            )
        except (subprocess.CalledProcessError, aiohttp.ClientResponseError) as e:
            self.log.error(f"Encountered error executing subprocess command: {e}")
            return None

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            self.log.error(f"Error decoding JSON data: {e}")
            return None

        os_versions = data.get("OSVersions", [])
        latest_versions = []
        for version in os_versions:
            version_info = version.get("Latest", {})
            latest_versions.append(
                {
                    "OSVersion": version.get("OSVersion"),
                    "ProductVersion": version_info.get("ProductVersion"),
                    "ReleaseDate": self.convert_timezone(
                        version_info.get("ReleaseDate")
                    ),
                }
            )
        return latest_versions
