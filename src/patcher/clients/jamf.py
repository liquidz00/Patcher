"""Client for the Jamf Pro API."""

import csv
import io
import json
from typing import Any

from pydantic import ValidationError

from ..core.config_manager import ConfigManager
from ..core.exceptions import APIResponseError
from ..core.logger import LogMe
from ..core.models.jamf import ApiClientModel, ApiRoleModel
from ..core.models.patch import PatchDevice, PatchTitle
from . import HTTPClient
from .token_manager import TokenManager


class JamfSetupClient(HTTPClient):
    """Credential-free Jamf client for the first-run provisioning flow (basic-token auth + API role/client creation)."""

    def __init__(self, jamf_url: str, max_concurrency: int = 5):
        """
        A Jamf client for the pre-credential setup flow.

        Unlike :class:`JamfClient`, it needs no stored credentials at
        construction (only the instance URL), because it runs *before* an API
        client exists; it is what mints one. Username/password and the basic
        token are passed per call to the provisioning methods.

        :param jamf_url: The Jamf Pro instance URL to provision against.
        :type jamf_url: str
        :param max_concurrency: Maximum number of concurrent API requests.
        :type max_concurrency: int
        """
        self.jamf_url = jamf_url
        self.log = LogMe(self.__class__.__name__)

        super().__init__(max_concurrency)

    # API calls for client setup
    async def fetch_basic_token(self, username: str, password: str) -> str:
        """
        Asynchronously retrieves a basic token using HTTP Basic authentication.

        This method is intended for initial setup to obtain client credentials for API
        clients and roles. It should not be used for regular token retrieval after setup.

        The password is passed via httpx's ``auth=`` tuple parameter, which encodes it
        in the ``Authorization`` header. It never appears in the URL, request body, or
        log output, so no credential-sanitization step is required on the error path.

        :param username: Username of admin Jamf Pro account for authentication. Not permanently stored, only used for initial token retrieval.
        :type username: str
        :param password: Password of admin Jamf Pro account. Not permanently stored, only used for initial token retrieval.
        :type password: str
        :returns: The BasicToken string.
        :rtype: str
        :raises APIResponseError: If the call is unauthorized, unsuccessful, or the response body doesn't contain a ``token`` field.
        """
        self.log.debug("Attempting to retrieve Basic Token with provided credentials.")
        token_url = f"{self.jamf_url}/api/v1/auth/token"

        response = await self._request(
            "POST", token_url, auth=(username, password), headers={"accept": "application/json"}
        )

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise APIResponseError(
                "Failed parsing basic token response",
                username=username,
                url=self.jamf_url,
                status_code=response.status_code,
                error_msg=str(e),
            )

        if response.is_success and data and "token" in data:
            self.log.info("Basic Token retrieved successfully.")
            return data["token"]

        raise APIResponseError(
            "Unable to retrieve basic token with provided username and password",
            username=username,
            url=self.jamf_url,
            status_code=response.status_code,
        )

    async def create_roles(self, token: str) -> bool:
        """
        Creates the necessary API roles using the provided basic token.

        .. seealso::
            :class:`~patcher.core.models.jamf.ApiRoleModel`

        :param token: The basic token to use for authentication.
        :type token: str
        :return: True if roles were successfully created, False otherwise.
        :rtype: bool
        """
        self.log.debug("Attempting to create Patcher API Role via Jamf API.")
        role = ApiRoleModel()
        payload = {
            "displayName": role.display_name,
            "privileges": role.privileges,
        }

        role_url = f"{self.jamf_url}/api/v1/api-roles"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        response = await self.fetch_json(url=role_url, headers=headers, method="POST", data=payload)

        if response.get("displayName") == role.display_name:
            self.log.info("Patcher API Role created successfully.")
            return True
        else:
            self.log.warning("Failed to create Patcher API role as expected.")
            return False

    async def create_client(self, token: str) -> tuple[str, str]:
        """
        Creates an API client and retrieves its client ID and client secret.

        .. seealso::
            :class:`~patcher.core.models.jamf.ApiClientModel`

        :param token: The basic token to use for authentication.
        :type token: str
        :return: A tuple containing the client ID and client secret.
        :rtype: tuple[str, str]
        """
        self.log.debug("Attempting to create Patcher API Client with Jamf API.")
        client = ApiClientModel()
        client_url = f"{self.jamf_url}/api/v1/api-integrations"
        payload = {
            "authorizationScopes": client.auth_scopes,
            "displayName": client.display_name,
            "enabled": client.enabled,
            "accessTokenLifetimeSeconds": client.token_lifetime,
        }

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        response = await self.fetch_json(
            url=client_url, method="POST", data=payload, headers=headers
        )

        client_id = response.get("clientId")
        integration_id = response.get("id")  # Required for integration API call
        self.log.info("Created Patcher API Client ID successfully.")

        # Obtain client secret
        self.log.debug("Attempting to retrieve Patcher API Client Secret from Jamf API.")
        secret_url = f"{self.jamf_url}/api/v1/api-integrations/{integration_id}/client-credentials"
        secret_response = await self.fetch_json(url=secret_url, method="POST", headers=headers)
        client_secret = secret_response.get("clientSecret")
        self.log.info("Retrieved Patcher API Client Secret successfully.")

        # Return credentials
        return client_id, client_secret


class JamfClient(HTTPClient):
    """Fetches patch-management data, device inventory, and OS versions from Jamf Pro."""

    def __init__(self, config: ConfigManager, concurrency: int):
        """
        Provides methods for interacting with the Jamf API, specifically fetching patch data, device information, and OS versions.

        .. note::
            All methods of the JamfClient class will raise an :exc:`~patcher.core.exceptions.APIResponseError` if the API call is unsuccessful.

        :param config: Instance of ``ConfigManager`` for loading and storing credentials.
        :type config: :class:`~patcher.core.config_manager.ConfigManager`
        :param concurrency: Maximum number of concurrent API requests. See :ref:`concurrency <concurrency>` in Usage docs.
        :type concurrency: int
        """
        self.log = LogMe(self.__class__.__name__)
        self.config = config
        self.token_manager = TokenManager(config)

        # Creds can be loaded here as JamfClient objects can only exist after successful JamfClient creation.
        self.jamf_credentials = self.token_manager.attach_client()
        self.jamf_url = self.jamf_credentials.base_url

        super().__init__(max_concurrency=concurrency)

    async def aclose(self) -> None:
        """Release this client's connection pool and the token manager's."""
        await self.token_manager.aclose()
        await super().aclose()

    @classmethod
    def from_credentials(
        cls,
        client_id: str,
        client_secret: str,
        server: str,
        concurrency: int = 5,
    ) -> "JamfClient":
        """
        Construct an :class:`JamfClient` directly from credentials, bypassing
        the macOS keychain. Intended for library and CI/CD use.

        Wraps the inputs in an in-memory :class:`~patcher.core.config_manager.ConfigManager`
        (the same path the CLI uses for non-interactive mode) so no keyring
        backend is required and nothing is persisted to disk.

        .. code-block:: python

            from patcher import JamfClient

            client = JamfClient.from_credentials(
                client_id="...",
                client_secret="...",
                server="https://myorg.jamfcloud.com",
            )
            summaries = await client.get_summaries(await client.get_policies())

        :param client_id: Jamf Pro API client ID.
        :type client_id: str
        :param client_secret: Jamf Pro API client secret.
        :type client_secret: str
        :param server: Jamf Pro instance URL (e.g. ``https://myorg.jamfcloud.com``).
        :type server: str
        :param concurrency: Maximum concurrent API requests. Defaults to 5,
            the recommended ceiling per the
            `Jamf Developer Guide <https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices>`_.
        :type concurrency: int
        :return: A constructed ``JamfClient`` ready for use.
        :rtype: :class:`JamfClient`
        """
        config = ConfigManager(
            in_memory_credentials={
                "CLIENT_ID": client_id,
                "CLIENT_SECRET": client_secret,
                "URL": server,
            }
        )
        return cls(config=config, concurrency=concurrency)

    async def _headers(self) -> dict[str, str]:
        """Generates headers for API calls, ensuring the latest token is used."""
        # Ensure token is valid
        await self.token_manager.ensure_valid_token()
        latest_token = self.token_manager.token
        plaintext = latest_token.token.get_secret_value()
        self.log.debug(f"Using token ending in {plaintext[-4:]}")
        return {"accept": "application/json", "Authorization": f"Bearer {plaintext}"}

    async def get_title_configs(self) -> list[dict]:
        """
        Fetch the full patch software title configurations.

        .. important::
            Each config carries ``id`` and ``softwareTitleNameId`` which are easy to conflate.
            ``softwareTitleNameId`` is the global catalog code used for deterministic matching.
        """
        headers = await self._headers()
        url = f"{self.jamf_url}/api/v2/patch-software-title-configurations"
        return await self.fetch_json(url=url, headers=headers)

    async def get_policies(self) -> list[str]:
        """Retrieve the list of patch software title IDs from the Jamf API."""
        return [config.get("id") for config in await self.get_title_configs()]

    async def get_summaries(self, policy_ids: list[str]) -> list[PatchTitle]:
        """
        Retrieves patch summaries asynchronously for the specified policy IDs from the Jamf API.

        :param policy_ids: list of policy IDs to retrieve summaries for.
        :type policy_ids: list[str]
        :return: list of ``PatchTitle`` objects containing patch summaries.
        :rtype: list[:class:`~patcher.core.models.patch.PatchTitle`]
        """
        urls = [
            f"{self.jamf_url}/api/v2/patch-software-title-configurations/{policy}/patch-summary"
            for policy in policy_ids
        ]
        headers = await self._headers()
        summaries = await self.fetch_batch(urls, headers=headers)

        patch_titles = [
            PatchTitle(
                title=summary.get("title"),
                title_id=summary.get("softwareTitleId"),
                released=summary.get("releaseDate"),
                hosts_patched=summary.get("upToDate"),
                missing_patch=summary.get("outOfDate"),
                latest_version=summary.get("latestVersion"),
            )
            for summary in summaries
            if summary
        ]
        return patch_titles

    async def get_title_report_csv(self, title_id: str) -> list[PatchDevice]:
        """
        Retrieve the complete patch report for a specific software title using the CSV export endpoint.

        This method fetches all device data in a single CSV request, avoiding pagination entirely.

        :param title_id: The software title ID to retrieve the patch report for.
        :type title_id: str
        :return: List of all PatchDevice objects for the title.
        :rtype: list[:class:`~patcher.core.models.patch.PatchDevice`]
        :raises APIResponseError: If the CSV export fails or returns non-200 status.
        """
        headers = await self._headers()
        headers["accept"] = "text/csv"
        export_url = (
            f"{self.jamf_url}/api/v2/patch-software-title-configurations/{title_id}/export-report"
        )

        csv_columns = [
            "computerName",
            "deviceId",
            "username",
            "operatingSystemVersion",
            "lastContactTime",
            "buildingName",
            "departmentName",
            "siteName",
            "version",
        ]
        # list-of-tuples form preserves repeated `columns-to-export` keys;
        # httpx URL-encodes each pair on its own.
        query_params = [("columns-to-export", col) for col in csv_columns]

        try:
            csv_body = await self.fetch_text(export_url, headers=headers, params=query_params)
        except APIResponseError as e:
            self.log.error(f"Failed to fetch CSV export for title {title_id}: {e}")
            raise APIResponseError(
                "Failed to export patch report for title.", title_id=title_id, error_msg=str(e)
            )

        devices = []
        csv_reader = csv.DictReader(io.StringIO(csv_body))

        for row in csv_reader:
            try:
                device = PatchDevice(**row)
                devices.append(device)
            except (ValidationError, TypeError) as e:
                self.log.warning(f"Failed to parse device row: {e}")
                continue

        self.log.info(f"Collected {len(devices)} devices from CSV export for title {title_id}")
        return devices

    async def get_title_reports(self, title_ids: list[str]) -> dict[str, list[PatchDevice]]:
        """
        Retrieves patch reports for multiple software titles.

        Processes titles sequentially to avoid overwhelming the Jamf API. Each title's
        pagination is handled by the underlying stream/fetch methods.

        :param title_ids: List of software title IDs to retrieve reports for.
        :type title_ids: list[str]
        :return: Dictionary mapping title IDs to lists of PatchDevice objects.
        :rtype: dict[str, list[:class:`~patcher.core.models.patch.PatchDevice`]]
        """
        self.log.debug(f"Fetching patch reports for {len(title_ids)} titles")
        results = {}

        for title_id in title_ids:
            self.log.info(f"Processing patch report for title {title_id}")

            try:
                title_devices = await self.get_title_report_csv(title_id)
                results[title_id] = title_devices
            except APIResponseError as e:
                self.log.error(f"Failed to fetch report for title {title_id}: {e}")
                results[title_id] = []

        total_devices = sum(len(devices) for devices in results.values())
        self.log.info(f"Collected {total_devices} total devices across {len(title_ids)} titles")
        return results

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
        response = await self.fetch_json(url=url, headers=headers)
        devices = response.get("results")
        return [device.get("id") for device in devices if device]

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
        subsets = await self.fetch_batch(urls, headers=headers)

        devices = [
            {
                "SN": subset.get("serialNumber"),
                "OS": subset.get("osVersion"),
            }
            for subset in subsets
            if subset
        ]
        return devices

    async def get_app_names(self, patch_titles: list[PatchTitle]) -> list[dict[str, Any]]:
        """
        Fetches all possible app names for each ``PatchTitle`` object provided.

        :param patch_titles: list of ``PatchTitle`` objects.
        :type patch_titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
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
