import asyncio
import json
import subprocess
from typing import Any
from urllib.parse import urlencode

import httpx

from ..models.jamf_client import ApiClientModel, ApiRoleModel
from ..utils.exceptions import APIResponseError, PatcherError, ShellCommandError
from ..utils.logger import LogMe


class BaseAPIClient:
    def __init__(self, max_concurrency: int = 5):
        """
        The BaseAPIClient class controls concurrency settings and secure connections for *all* API calls.

        This class forms the backbone of Patcher's ability to interact with external APIs.
        It manages the number of API requests that can be made simultaneously, ensuring the tool is both
        efficient and does not overload any servers.

        .. warning::
            Changing the max_concurrency value could lead to your Jamf server being unable to perform other basic tasks.
            It is **strongly recommended** to limit API call concurrency to no more than 5 connections.
            See `Jamf Developer Guide <https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices>`_ for more information.

        :param max_concurrency: The maximum number of API requests that can be sent at once. Defaults to ``5``.
        :type max_concurrency: int
        """
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.default_headers = {"accept": "application/json", "Content-Type": "application/json"}
        self.log = LogMe(self.__class__.__name__)
        # Lazily-constructed httpx.AsyncClient. See the ``http`` property.
        self._http_client: httpx.AsyncClient | None = None
        self.log.debug(f"BaseAPIClient initialized with max_concurrency: {max_concurrency}")

    @property
    def concurrency(self) -> int:
        """
        Gets the current concurrency setting used by Patcher.

        :return: The maximum number of concurrent API requests that can be made.
        :rtype: int
        """
        return self.max_concurrency

    @concurrency.setter
    def concurrency(self, concurrency: int) -> None:
        """
        Sets the maximum concurrency level for API calls.

        This method allows you to set the maximum number of concurrent API calls
        that can be made by the Jamf client. It is recommended to limit this value
        to 5 connections to avoid overloading the Jamf server.

        :param concurrency: The new maximum concurrency level.
        :type concurrency: int
        :raises PatcherError: If the concurrency level is less than 1.
        """
        if concurrency < 1:
            raise PatcherError("Concurrency level must be at least 1.")
        self.max_concurrency = concurrency

    @property
    def http(self) -> httpx.AsyncClient:
        """
        Lazily-constructed :class:`httpx.AsyncClient` bound to this BaseAPIClient instance.

        First access constructs the client; subsequent accesses return the same
        instance. Call :meth:`aclose` to release the underlying connection pool
        when this BaseAPIClient is no longer needed. The CLI doesn't strictly
        need to call ``aclose`` (process exit reclaims resources), but library
        consumers should for clean shutdown.

        :return: The shared ``httpx.AsyncClient`` for this instance.
        :rtype: httpx.AsyncClient

        .. note::
            Not thread-safe. BaseAPIClient is intended for single-event-loop use.
            ``max_connections`` is bound to ``self.max_concurrency`` so the same
            ceiling that gates ``self.semaphore`` (used by curl-based methods)
            also applies at the HTTP layer.
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=self.max_concurrency),
                follow_redirects=True,
            )
        return self._http_client

    async def aclose(self) -> None:
        """
        Release the underlying httpx connection pool, if one was created.

        Idempotent: safe to call multiple times. After calling, the next
        access to :attr:`http` will construct a fresh client.
        """
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def fetch_text(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> str:
        """
        Fetch the body of a URL as text via httpx.

        Translates httpx-native errors to Patcher's :class:`APIResponseError`
        so callers see the same exception contract as the existing
        :meth:`fetch_json` path — notably the ``not_found=True`` flag on 404
        responses, which :meth:`patcher.utils.installomator.Installomator.match`
        uses to short-circuit gracefully.

        :param url: The URL to fetch.
        :type url: str
        :param headers: Optional request headers. If omitted, only httpx
            defaults are sent.
        :type headers: dict[str, str] | None
        :return: The response body as a string.
        :rtype: str
        :raises APIResponseError: If the response is non-2xx, or if a
            network-level error (connect, DNS, timeout) prevents the
            request from completing. ``not_found=True`` is set on 404.
        """
        self.log.debug(f"Fetching text from {url}")
        try:
            async with self.semaphore:
                response = await self.http.get(url, headers=headers)
        except httpx.RequestError as e:
            raise APIResponseError(
                "Network error fetching URL",
                url=url,
                error_msg=str(e),
            )

        if response.status_code == 404:
            raise APIResponseError(
                "Requested resource was not found.",
                url=url,
                status_code=response.status_code,
                not_found=True,
            )
        if not response.is_success:
            raise APIResponseError(
                "Non-success HTTP status received.",
                url=url,
                status_code=response.status_code,
            )

        return response.text

    @staticmethod
    def _format_headers(headers: dict[str, str]) -> list[str]:
        """Formats headers properly for curl commands."""
        formatted_headers = []
        for k, v in headers.items():
            formatted_headers.extend(["-H", f"{k}: {v}"])
        return formatted_headers

    def _handle_status_code(self, status_code: int, response_json: dict | None) -> dict:
        """Handles HTTP status codes and returns the appropriate response or raises errors."""
        self.log.debug(f"Parsing API response. (status code: {status_code})")

        if 200 <= status_code < 300:
            self.log.info("API call successful.")
            return response_json

        # Propagate logs to caller
        error_message = (
            response_json.get("errors", "Unknown error") if response_json else "No details"
        )
        if status_code == 404:
            raise APIResponseError(
                "Requested resource was not found.",
                status_code=status_code,
                error=error_message,
                not_found=True,  # distinguish 404 errors
            )
        elif 400 <= status_code < 500:
            raise APIResponseError(
                "Client error received.", status_code=status_code, error=error_message
            )
        elif 500 <= status_code < 600:
            raise APIResponseError(
                "Server error received.", status_code=status_code, error=error_message
            )
        else:
            raise APIResponseError(
                "Unexpected HTTP status code received.",
                status_code=status_code,
                error=error_message,
            )

    @staticmethod
    def _sanitize_command(command: list[str]) -> list[str]:
        """Sanitizes sensitive data in the command list."""
        sensitive_keys = {"client_id", "client_secret", "password", "username"}
        sanitized = []
        skip_next = False  # Handle values immediately following specific flags (e.g., -u)

        for _, part in enumerate(command):
            if skip_next:
                sanitized.append("<REDACTED_CREDENTIAL>")
                skip_next = False
                continue

            if part == "-u":
                sanitized.append(part)
                skip_next = True
            elif "Bearer" in part:
                sanitized.append("<REDACTED_TOKEN>")
            elif any(f"{key}=" in part for key in sensitive_keys):
                key, value = part.split("=", 1)
                sanitized.append(f"{key}=<REDACTED_CREDENTIAL>")
            else:
                sanitized.append(part)

        return sanitized

    async def execute(self, command: list[str]) -> dict | str:
        """
        Asynchronously executes a shell command using subprocess and returns the output.

        This method leverages asyncio to run a command in a new subprocess. If the
        command execution is unsuccessful (non-zero return code), an exception is raised.

        .. note::
            This method should be used for executing shell commands that are essential to the
            functionality of the API client, such as invoking cURL commands for API calls.

        :param command: A list representing the command and its arguments to be executed in the shell.
        :type command: list[str]
        :return: The standard output of the executed command decoded as a string.
        :rtype: dict | str
        :raises ShellCommandError: If the command execution fails (returns a non-zero exit code).
        """
        sanitized_command = self._sanitize_command(command)
        sanitized_command_str = " ".join(sanitized_command).replace("\n", "")
        self.log.debug(f"Attempting to execute {sanitized_command_str} command asynchronously")
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                error_msg = stderr.decode().strip()
                raise ShellCommandError(
                    "Command execution failed.",
                    command=command,
                    error=error_msg,
                    return_code=process.returncode,
                )
            self.log.info("Command executed as expected with zero exit code status.")
            return stdout.decode().strip()
        except OSError as e:
            raise ShellCommandError(
                "OSError encountered executing command.",
                command=sanitized_command_str,
                error_msg=str(e),
            )

    def execute_sync(self, command: list[str]) -> bytes | str:
        """
        Identical to ``execute`` method, but does not leverage async functionality.

        Method is primarily intended for :class:`~patcher.client.ui_manager.UIConfigManager` to ensure default font files are downloaded properly. See :meth:`~patcher.client.ui_manager.UIConfigManager._download_font` for details.

        .. important::

            If used in separate context from downloading font files, output **needs to be decoded from bytes**:

            .. code-block:: python

                b = BaseAPIClient()
                result = b.execute_sync(["/usr/bin/curl", "-s", "-L", "https://ifconfig.co"])  # Returns <class 'bytes'>
                decoded = result.decode().strip()  # Returns <class 'str'>

        :param command: A list representing the command and its arguments to be executed in the shell.
        :type command: list[str]
        :return: The standard output of the executed command decoded as a string.
        :rtype: bytes | str
        :raises ShellCommandError: If the command execution fails (returns a non-zero exit code).
        """
        sanitized_command = self._sanitize_command(command)
        sanitized_command_str = " ".join(sanitized_command).replace("\n", "")
        self.log.debug(f"Attempting to execute {sanitized_command_str} command (no async).")
        try:
            result = subprocess.run(
                command,  # subprocess expects unpacked list
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return result.stdout
        except (subprocess.CalledProcessError, OSError) as e:
            error_msg = e.stderr.decode("utf-8", errors="replace").strip()
            raise ShellCommandError(
                "Command execution failed.",
                return_code=e.returncode,
                error_msg=error_msg,
                command=sanitized_command_str,
            )

    async def fetch_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        data: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> dict:
        """
        Asynchronously fetches JSON data from the specified URL using the specified HTTP method.

        Routes the request through the per-instance ``httpx.AsyncClient`` (see
        :attr:`http`). Form-encoded vs JSON request bodies are selected based
        on the ``Content-Type`` header of the merged request headers — the
        same routing logic the prior curl-based implementation used. Non-2xx
        responses are translated via :meth:`_handle_status_code` into
        :class:`APIResponseError` (with ``not_found=True`` on 404), preserving
        the public exception contract for callers.

        :param url: The URL to fetch data from.
        :type url: str
        :param headers: Optional headers to include in the request. Defaults to ``self.default_headers``.
        :type headers: dict[str, str] | None
        :param method: HTTP method to use ("GET" or "POST"). Defaults to "GET".
        :type method: str
        :param data: Optional request body. Form-encoded when the request
            ``Content-Type`` is ``application/x-www-form-urlencoded``;
            JSON-encoded otherwise.
        :type data: dict[str, str] | None
        :param query_params: Additional query parameters to append to the URL.
        :type query_params: dict[str, str] | None
        :return: The decoded JSON response body.
        :rtype: dict
        :raises APIResponseError: If the response is non-2xx, if a network error
            prevents the request from completing, or if the response body is
            not valid JSON.
        """
        self.log.debug("Attempting to fetch JSON.")

        final_headers = headers if headers else self.default_headers
        method_upper = method.upper()

        request_kwargs: dict[str, Any] = {
            "url": url,
            "headers": final_headers,
        }
        if query_params:
            request_kwargs["params"] = query_params

        # Form-encoded vs JSON body routing mirrors the prior curl logic:
        # if the caller set Content-Type=application/x-www-form-urlencoded
        # we pass `data=` (httpx form-encodes); otherwise we pass `json=`
        # (httpx serializes + sets Content-Type=application/json).
        if method_upper == "POST" and data:
            self.log.debug("Adding POST data to the request.")
            if final_headers.get("Content-Type") == "application/x-www-form-urlencoded":
                request_kwargs["data"] = data
            else:
                request_kwargs["json"] = data

        try:
            async with self.semaphore:
                response = await self.http.request(method_upper, **request_kwargs)
        except httpx.RequestError as e:
            raise APIResponseError(
                "Network error fetching URL",
                url=url,
                error_msg=str(e),
            )

        try:
            response_json = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise APIResponseError(
                "Failed parsing JSON response from API",
                url=url,
                status_code=response.status_code,
                error_msg=str(e),
            )

        self.log.info("Retrieved valid JSON response API call.")
        return self._handle_status_code(response.status_code, response_json)

    async def fetch_batch(
        self,
        urls: list[str],
        headers: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> list[dict]:
        """
        Fetches JSON data in batches to respect the concurrency limit.

        Data is fetched from each URL in the provided list, ensuring that no more than ``max_concurrency`` requests are sent concurrently.

        :param urls: list of URLs to fetch data from.
        :type urls: list[str]
        :param headers: Optional headers to include in the request. Defaults to ``self.headers`` via the :meth:`~patcher.client.__init__.fetch_json` method.
        :type headers: dict[str, str] | None
        :param query_params: Additional query parameters to append to the URL. Defaults to None.
        :type query_params: dict[str, str] | None
        :return: A list of JSON dictionaries.
        :rtype: list[dict]
        """
        self.log.debug(f"Attempting to fetch batch of {len(urls)} URLs")

        if query_params:
            query_string = urlencode(query_params)
            urls = [f"{url}?{query_string}" for url in urls]

        results = []
        for i in range(0, len(urls), self.max_concurrency):
            batch = urls[i : i + self.max_concurrency]
            tasks = [self.fetch_json(url, headers=headers) for url in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
        return results

    # API calls for client setup
    async def fetch_basic_token(self, username: str, password: str, jamf_url: str) -> str:
        """
        Asynchronously retrieves a basic token using basic authentication.

        This method is intended for initial setup to obtain client credentials for API clients and roles.
        It should not be used for regular token retrieval after setup.

        :param username: Username of admin Jamf Pro account for authentication. Not permanently stored, only used for initial token retrieval.
        :type username: str
        :param password: Password of admin Jamf Pro account. Not permanently stored, only used for initial token retrieval.
        :type password: str
        :param jamf_url: Jamf Server URL (See :attr:`~patcher.models.jamf_client.JamfClient.server`).
        :type jamf_url: str
        :returns: The BasicToken string.
        :rtype: str
        :raises APIResponseError: If the call is unauthorized or unsuccessful.
        """
        self.log.debug("Attempting to retrieve Basic Token with provided credentials.")
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
            resp = await self.execute(command)
            response = json.loads(resp)
            if response and "token" in response:
                self.log.info("Basic Token retrieved successfully.")
                return response.get("token")
            else:
                sanitized = self._sanitize_command(command)
                raise APIResponseError(
                    "Unable to retrieve basic token with provided username and password",
                    username=username,
                    url=jamf_url,
                    command=sanitized,
                )

    async def create_roles(self, token: str, jamf_url: str) -> bool:
        """
        Creates the necessary API roles using the provided basic token.

        .. seealso::
            :class:`~patcher.models.jamf_client.ApiRoleModel`

        :param token: The basic token to use for authentication.
        :type token: str
        :param jamf_url: Jamf Server URL
        :type jamf_url: str
        :return: True if roles were successfully created, False otherwise.
        :rtype: bool
        """
        self.log.debug("Attempting to create Patcher API Role via Jamf API.")
        role = ApiRoleModel()
        payload = {
            "displayName": role.display_name,
            "privileges": role.privileges,
        }

        role_url = f"{jamf_url}/api/v1/api-roles"
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

    async def create_client(self, token: str, jamf_url: str) -> tuple[str, str]:
        """
        Creates an API client and retrieves its client ID and client secret.

        .. seealso::
            :class:`~patcher.models.jamf_client.ApiClientModel`

        :param token: The basic token to use for authentication.
        :type token: str
        :param jamf_url: Jamf Server URL
        :type jamf_url: str
        :return: A tuple containing the client ID and client secret.
        :rtype: tuple[str, str]
        """
        self.log.debug("Attempting to create Patcher API Client with Jamf API.")
        client = ApiClientModel()
        client_url = f"{jamf_url}/api/v1/api-integrations"
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
        secret_url = f"{jamf_url}/api/v1/api-integrations/{integration_id}/client-credentials"
        secret_response = await self.fetch_json(url=secret_url, method="POST", headers=headers)
        client_secret = secret_response.get("clientSecret")
        self.log.info("Retrieved Patcher API Client Secret successfully.")

        # Return credentials
        return client_id, client_secret
