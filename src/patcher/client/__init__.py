import asyncio
import json
import subprocess
from typing import Dict, List, Optional, Tuple, Union

from ..models.jamf_client import ApiClientModel, ApiRoleModel
from ..utils.exceptions import APIResponseError, PatcherError, ShellCommandError
from ..utils.logger import LogMe


class BaseAPIClient:
    """
    The BaseAPIClient class controls concurrency settings and secure connections for *all* API calls.

    This class forms the backbone of Patcher's ability to interact with external APIs.
    It manages the number of API requests that can be made simultaneously, ensuring the tool is both
    efficient and does not overload any servers.

    .. warning::
        Changing the max_concurrency value could lead to your Jamf server being unable to perform other basic tasks.
        It is **strongly recommended** to limit API call concurrency to no more than 5 connections.
        See `Jamf Developer Guide <https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices>`_ for more information.

    """

    def __init__(self, max_concurrency: int = 5):
        """
        Initializes the BaseAPIClient class with default settings.

        :param max_concurrency: The maximum number of API requests that can be sent at once. Defaults to 5.
        :type max_concurrency: int
        """
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.default_headers = {"accept": "application/json", "Content-Type": "application/json"}
        self.log = LogMe(self.__class__.__name__)
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
        :raises ValueError: If the concurrency level is less than 1.
        """
        if concurrency < 1:
            raise PatcherError("Concurrency level must be at least 1.")
        self.max_concurrency = concurrency

    @staticmethod
    def _format_headers(headers: Dict[str, str]) -> List[str]:
        """Formats headers properly for curl commands."""
        formatted_headers = []
        for k, v in headers.items():
            formatted_headers.extend(["-H", f"{k}: {v}"])
        return formatted_headers

    def _handle_status_code(
        self, status_code: int, response_json: Optional[Dict]
    ) -> Optional[Dict]:
        """Handles HTTP status codes and returns the appropriate response or raises errors."""
        self.log.debug(f"Parsing API response. (status code: {status_code})")

        if 200 <= status_code < 300:
            self.log.info("API call successful.")
            return response_json

        error_message = (
            response_json.get("errors", "Unknown error") if response_json else "No details"
        )
        if 400 <= status_code < 500:
            self.log.error(f"Client error ({status_code}): {error_message}")
            raise APIResponseError(
                "Client error received.", status_code=status_code, error=error_message
            )
        elif 500 <= status_code < 600:
            self.log.error(f"Server error ({status_code}): {error_message}")
            raise APIResponseError(
                "Server error received.", status_code=status_code, error=error_message
            )
        else:
            self.log.error(f"Unexpected HTTP status code ({status_code}): {error_message}")
            raise APIResponseError(
                "Unexpected HTTP status code received.",
                status_code=status_code,
                error=error_message,
            )

    @staticmethod
    def _sanitize_command(command: List[str]) -> List[str]:
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

    async def execute(self, command: List[str]) -> Optional[Union[Dict, str]]:
        """
        Asynchronously executes a shell command using subprocess and returns the output.

        This method leverages asyncio to run a command in a new subprocess. If the
        command execution is unsuccessful (non-zero return code), an exception is raised.

        .. note::
            This method should be used for executing shell commands that are essential to the
            functionality of the API client, such as invoking cURL commands for API calls.

        :param command: A list representing the command and its arguments to be executed in the shell.
        :type command: List[str]
        :return: The standard output of the executed command decoded as a string, or None if there is an error.
        :rtype: Optional[Union[Dict, str]]
        :raises exceptions.ShellCommandError: If the command execution fails (returns a non-zero exit code).
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
                self.log.error(
                    f"Command execution failed. Return code: {process.returncode}, Error: {error_msg}"
                )
                raise ShellCommandError(
                    "Command execution failed.",
                    command=command,
                    error=error_msg,
                    return_code=process.returncode,
                )
            self.log.info("Command executed as expected with zero exit code status.")
            return stdout.decode().strip()
        except OSError as e:
            self.log.error(f"OSError encountered executing command. Details: {e}")
            raise ShellCommandError(
                "OSError encountered executing command.",
                command=command,
                error_msg=str(e),
            )

    async def fetch_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        method: str = "GET",
        data: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """
        Asynchronously fetches JSON data from the specified URL using a specified HTTP method.

        :param url: The URL to fetch data from.
        :type url: str
        :param headers: Optional headers to include in the request.
        :type headers: Optional[Dict[str, str]]
        :param method: HTTP method to use ("GET" or "POST"). Defaults to "GET".
        :type method: str
        :param data: Optional form data to include for POST request.
        :type data: Optional[Dict[str, str]]
        :return: The fetched JSON data as a dictionary, or None if the request fails.
        :rtype: Optional[Dict]
        :raises APIResponseError: If the response payload is not valid JSON, or if command execution fails.
        """
        self.log.debug(f"Attempting to fetch JSON from {url}")
        final_headers = headers if headers else self.default_headers
        header_string = self._format_headers(final_headers)

        # By using the -w parameter with %{http_code}, we are appending the status code
        # to the end of the API response. This is to handle cases where responses
        # do not have 'httpStatus' keys by default.
        command = [
            "/usr/bin/curl",
            "-s",
            "-X",
            method,
            url,
            *header_string,
            "-w",
            "\nSTATUS:%{http_code}",
        ]

        # Add form data for POST requests
        if method.upper() == "POST" and data:
            self.log.debug("Adding POST data to the request.")
            if final_headers.get("Content-Type") == "application/x-www-form-urlencoded":
                # Format each item separately instead
                form_data = [item for k, v in data.items() for item in ["-d", f"{k}={v}"]]
                command.extend(form_data)
            else:
                # JSON is assumed for other content types
                json_payload = json.dumps(data)
                command.extend(["-d", json_payload])

        async with self.semaphore:
            output = await self.execute(command)

        try:
            # Separate status code from body of response
            response_body, status_line = output.rsplit("\nSTATUS:", 1)
            status_code = int(status_line.strip())
            response_json = json.loads(response_body)  # Re-parse body as JSON
        except (json.JSONDecodeError, ValueError) as e:
            sanitized = self._sanitize_command(command)
            self.log.error(f"Failed to parse JSON response from {url} via command. Details: {e}")
            raise APIResponseError(
                "Failed parsing JSON response from API",
                url=url,
                command=sanitized,
                error_msg=str(e),
            )

        self.log.info(f"Retrieved JSON response from {url}.")
        return self._handle_status_code(status_code, response_json)

    async def fetch_batch(
        self, urls: List[str], headers: Optional[Dict[str, str]] = None
    ) -> List[Optional[Dict]]:
        """
        Fetches JSON data in batches to respect the concurrency limit. Data is fetched
        from each URL in the provided list, ensuring that no more than ``max_concurrency``
        requests are sent concurrently.

        :param urls: List of URLs to fetch data from.
        :type urls: List[str]
        :param headers:
        :type headers: Optional[Dict[str, str]] = None
        :return: A list of JSON dictionaries or None for URLs that fail to retrieve data.
        :rtype: List[Optional[Dict]]
        """
        self.log.info(f"Attempting to fetch batch of {len(urls)} URLs")
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
        Asynchronously retrieves a bearer token using basic authentication.

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
                self.log.error(
                    f"Unable to retrieve basic token with provided username ({username}) and password."
                )
                raise APIResponseError(
                    "Unable to retrieve basic token with provided username and password",
                    username=username,
                    url=jamf_url,
                    command=sanitized,
                )

    async def create_roles(self, token: str, jamf_url: str) -> bool:
        """
        Creates the necessary API roles using the provided bearer token.

        :param token: The bearer token to use for authentication. Defaults to the stored token if not provided.
        :type token: Optional[str]
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
            self.log.error("Failed to create Patcher API role as expected.")
            return False

    async def create_client(self, token: str, jamf_url: str) -> Optional[Tuple[str, str]]:
        """
        Creates an API client and retrieves its client ID and client secret.

        :param token: The bearer token to use for authentication. Defaults to the stored token if not provided.
        :type token: Optional[str]
        :param jamf_url: Jamf Server URL
        :type jamf_url: str
        :return: A tuple containing the client ID and client secret.
        :rtype: Optional[Tuple[str, str]]
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
