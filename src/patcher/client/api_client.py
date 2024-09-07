import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..models.jamf_client import ApiClientModel, ApiRoleModel
from ..models.patch import PatchTitle
from ..utils import logger
from ..utils.wrappers import check_token
from . import BaseAPIClient
from .config_manager import ConfigManager
from .token_manager import TokenManager


class ApiClient(BaseAPIClient):
    """
    Provides methods for interacting with the Jamf API, specifically fetching patch data, device information, and OS versions.

    The ``ApiClient`` manages authentication and session handling, ensuring efficient and secure communication with the Jamf API.
    """

    def __init__(self, config: ConfigManager, concurrency: int):
        """
        Initializes the ApiClient with the provided :class:`~patcher.client.config_manager.ConfigManager`.

        This sets up the API client with necessary credentials and session parameters for interacting with the Jamf API.

        .. seealso::
            :mod:`~patcher.models.jamf_client`

        :param config: Instance of ConfigManager for loading and storing credentials.
        :type config: ConfigManager
        :raises ValueError: If the JamfClient configuration is invalid.
        """
        self.log = logger.LogMe(self.__class__.__name__)
        self.config = config

        self.jamf_client = config.attach_client()
        if not self.jamf_client:
            self.log.error("Invalid JamfClient configuration detected!")
            raise ValueError("Invalid JamfClient configuration detected!")

        self.jamf_url = self.jamf_client.base_url
        self.token_manager = TokenManager(config)

        super().__init__(max_concurrency=concurrency)

    def _convert_tz(self, utc_time_str: str) -> Optional[str]:
        """
        Converts a UTC time string to a formatted string without timezone information.

        :param utc_time_str: UTC time string in ISO 8601 format (e.g., "2023-08-09T12:34:56+0000").
        :type utc_time_str: str
        :return: Formatted date string (e.g., "Aug 09 2023") or None if the input format is invalid.
        :rtype: Optional[str]

        .. note::

            This function is primarily used 'privately' by methods and classes and is not designed to be called explicitly.

        """
        try:
            utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S%z")
            return utc_time.strftime("%b %d %Y")
        except ValueError as e:
            self.log.error(f"Invalid time format provided. Details: {e}")
            return None

    @check_token
    async def get_policies(self) -> Optional[List]:
        """
        Retrieves a list of patch software title IDs from the Jamf API. This function
        requires a valid authentication token, which is managed automatically.

        :return: A list of software title IDs or None if an error occurs.
        :rtype: Optional[List]
        """
        url = f"{self.jamf_url}/api/v2/patch-software-title-configurations"
        response = await self.fetch_json(url=url, headers=self.jamf_client.headers)

        # Verify response is list type as expected
        if not isinstance(response, list):
            self.log.error(
                f"Unexpected response format: expected a list, received {type(response)} instead."
            )
            return None

        # Check if all elements in the list are dictionaries
        if not all(isinstance(item, dict) for item in response):
            self.log.error("Unexpected response format: all items should be dictionaries.")
            return None

        self.log.info("Patch policies obtained as expected.")
        return [title.get("id") for title in response]

    @check_token
    async def get_summaries(self, policy_ids: List) -> Optional[List[PatchTitle]]:
        """
        Retrieves patch summaries for the specified policy IDs from the Jamf API. This function
        fetches data asynchronously and compiles the results into a list of ``PatchTitle`` objects.

        :param policy_ids: List of policy IDs to retrieve summaries for.
        :type policy_ids: List
        :return: List of ``PatchTitle`` objects containing patch summaries or None if an error occurs.
        :rtype: Optional[List[PatchTitle]]
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
        if not response:
            self.log.error(f"Error fetching device IDs from {url}")
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

    async def get_sofa_feed(self) -> Optional[List[Dict[str, str]]]:
        """
        Fetches iOS Data feeds from SOFA and extracts latest OS version information.
        To limit the amount of possible SSL verification checks, this method utilizes a subprocess call
        instead.
        This method is only called if the :ref:`iOS <ios>` option is passed to the CLI.

        :return: A list of dictionaries containing base OS versions, latest iOS versions and release dates,
                or None on error.
        :rtype: Optional[List[Dict[str, str]]]
        """
        command = ["/usr/bin/curl", "-s", "https://sofafeed.macadmins.io/v1/ios_data_feed.json"]
        result = await self.execute(command)

        os_versions = result.get("OSVersions", [])
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

    async def fetch_basic_token(
        self, username: str, password: str, jamf_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Asynchronously retrieves a bearer token using basic authentication.

        This method is intended for initial setup to obtain client credentials for API clients and roles.
        It should not be used for regular token retrieval after setup.

        :param username: Username of admin Jamf Pro account for authentication. Not permanently stored, only used for initial token retrieval.
        :type username: str
        :param password: Password of admin Jamf Pro account. Not permanently stored, only used for initial token retrieval.
        :type password: str
        :param jamf_url: Jamf Server URL (same as ``server_url`` in :mod:`patcher.models.jamf_client` class).
        :type jamf_url: Optional[str]
        :raises exceptions.TokenFetchError: If the call is unauthorized or unsuccessful.
        :returns: True if the basic token was successfully retrieved, False if unauthorized (e.g., due to SSO).
        :rtype: bool
        """
        jamf_url = jamf_url or self.jamf_url
        token_url = f"{jamf_url}/api/v1/auth/token"
        command = [
            "/usr/bin/curl",
            "-s",
            "-u",
            f"{username}:{password}",
            "-H",
            "accept: application/json",
            "-X",
            "POST",
            token_url,
        ]
        async with self.semaphore:
            response = await self.execute(command)
            if response and "token" in response:
                return response.get("token")
            return None

    async def create_roles(self, token: str) -> bool:
        """
        Creates the necessary API roles using the provided bearer token.

        :param token: The bearer token to use for authentication. Defaults to the stored token if not provided.
        :type token: Optional[str]
        :return: True if roles were successfully created, False otherwise.
        :rtype: bool
        """
        role = ApiRoleModel()
        payload = json.dumps(
            {
                "displayName": role.display_name,
                "privileges": role.privileges,
            }
        )
        role_url = f"{self.jamf_url}/api/v1/api-roles"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        header_string = " ".join([f"-H '{k}: {v}'" for k, v in headers.items()])
        command = ["/usr/bin/curl", "-s", header_string, "-d", payload, "-X", "POST", role_url]
        response = await self.execute(command)
        return response is not None

    async def create_client(self, token: str) -> Optional[Tuple[str, str]]:
        """
        Creates an API client and retrieves its client ID and client secret.

        This method uses the provided bearer token to create a new API client in the Jamf server.

        :param token: The bearer token to use for authentication. Defaults to the stored token if not provided.
        :type token: Optional[str]
        :return: A tuple containing the client ID and client secret.
        :rtype: Optional[Tuple[str, str]]
        """
        client = ApiClientModel()
        client_url = f"{self.jamf_url}/api/v1/api-integrations"
        payload = json.dumps(
            {
                "authorizationScopes": client.auth_scopes,
                "displayName": client.display_name,
                "enabled": client.enabled,
                "accessTokenLifetimeSeconds": client.token_lifetime,  # 30 minutes in seconds
            }
        )
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        header_string = " ".join([f"-H '{k}: {v}'" for k, v in headers.items()])
        command = ["/usr/bin/curl", "-s", header_string, "-d", payload, "-X", "POST", client_url]

        response = await self.execute(command)
        if not response or "clientId" not in response:
            return None

        client_id = response.get("clientId")
        integration_id = response.get("id")

        secret_url = f"{self.jamf_url}/api/v1/api-integrations/{integration_id}/client-credentials"
        secret_command = ["/usr/bin/curl", "-s", header_string, "-X", "POST", secret_url]
        secret_response = await self.execute(secret_command)

        if not secret_response or "clientSecret" not in secret_response:
            return None

        client_secret = secret_response.get("clientSecret")
        return client_id, client_secret
