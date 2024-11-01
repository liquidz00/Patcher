import asyncio
import json
import subprocess
from typing import Dict, List, Optional, Tuple, Union

from ..models.jamf_client import ApiClientModel, ApiRoleModel
from ..utils import exceptions, logger


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

    :param max_concurrency: The maximum number of API requests that can be sent at once. Defaults to 5.
    :type max_concurrency: int
    """

    def __init__(self, max_concurrency: int = 5):
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.default_headers = {"accept": "application/json", "Content-Type": "application/json"}
        self.log = logger.LogMe(self.__class__.__name__)

    @property
    def concurrency(self) -> int:
        """
        Gets the current concurrency setting used by Patcher.

        :return: The maximum number of concurrent API requests that can be made.
        :rtype: int
        """
        return self.max_concurrency

    def set_concurrency(self, concurrency: int) -> None:
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
            raise ValueError("Concurrency level must be at least 1.")
        self.max_concurrency = concurrency

    def _handle_status_code(
        self, status_code: int, response_json: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Handles HTTP status codes and returns the appropriate response or raises errors.

        :param status_code: The HTTP status code to evaluate.
        :type status_code: int
        :param response_json: The parsed JSON response from the API.
        :type response_json: Optional[Dict]
        :return: The response if JSON is successful, otherwise raises an exception.
        :rtype: Optional[Dict]
        """
        if 200 <= status_code < 300:
            return response_json
        elif 400 <= status_code < 500:
            self.log.error(
                f"Client error ({status_code}): {response_json.get('errors', 'Unknown error')}"
            )
            raise exceptions.APIResponseError(
                f"Client error ({status_code}): {response_json.get('errors', 'Unknown error')}"
            )
        elif 500 <= status_code < 600:
            self.log.error(
                f"Server error ({status_code}): {response_json.get('errors', 'Unknown error')}"
            )
            raise exceptions.APIResponseError(
                f"Server error ({status_code}): {response_json.get('errors', 'Unknown error')}"
            )
        else:
            self.log.error(f"Unexpected HTTP status code {status_code}: {response_json}")
            raise exceptions.APIResponseError(
                f"Unexpected HTTP status code {status_code}: {response_json}"
            )

    @staticmethod
    def _format_headers(headers: Dict[str, str]) -> List[str]:
        """
        Formats headers properly for curl commands.

        :param headers: Dictionary of headers to format.
        :type headers: Dict[str, str]
        :return: List of formatted headers.
        :rtype: List[str]
        """
        formatted_headers = []
        for k, v in headers.items():
            formatted_headers.extend(["-H", f"{k}: {v}"])
        return formatted_headers

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
        process = await asyncio.create_subprocess_exec(
            *command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            self.log.error(f"Error executing subprocess command: {stderr.decode()}")
            raise exceptions.ShellCommandError(
                reason=f"Error executing subprocess command: {stderr.decode()}"
            )

        return stdout.decode()

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
        """
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

        # Separate status code from body of response
        try:
            response_body, status_line = output.rsplit("\nSTATUS:", 1)
            status_code = int(status_line.strip())
            response_json = json.loads(response_body)  # Re-parse body as JSON
        except (json.JSONDecodeError, ValueError) as e:
            self.log.error(f"Failed to decode JSON or parse status code from response: {e}")
            raise exceptions.APIResponseError(
                f"Failed to decode JSON or parse status code from response: {e}"
            )

        # Handle status code from response
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
        results = []
        for i in range(0, len(urls), self.max_concurrency):
            batch = urls[i : i + self.max_concurrency]
            tasks = [self.fetch_json(url, headers=headers) for url in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
        return results

    # API calls for client setup
    async def fetch_basic_token(self, username: str, password: str, jamf_url: str) -> Optional[str]:
        """
        Asynchronously retrieves a bearer token using basic authentication.

        This method is intended for initial setup to obtain client credentials for API clients and roles.
        It should not be used for regular token retrieval after setup.

        :param username: Username of admin Jamf Pro account for authentication. Not permanently stored, only used for initial token retrieval.
        :type username: str
        :param password: Password of admin Jamf Pro account. Not permanently stored, only used for initial token retrieval.
        :type password: str
        :param jamf_url: Jamf Server URL (same as ``server_url`` in :mod:`patcher.models.jamf_client` class).
        :type jamf_url: str
        :raises exceptions.TokenFetchError: If the call is unauthorized or unsuccessful.
        :returns: True if the basic token was successfully retrieved, False if unauthorized (e.g., due to SSO).
        :rtype: bool
        """
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
                return response.get("token")
            else:
                raise exceptions.TokenFetchError(
                    f"Unable to retrieve basic token with provided username ({username}) and password"
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
        return response.get("displayName") == role.display_name

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
        client = ApiClientModel()
        client_url = f"{jamf_url}/api/v1/api-integrations"
        payload = {
            "authorizationScopes": client.auth_scopes,
            "displayName": client.display_name,
            "enabled": client.enabled,
            "accessTokenLifetimeSeconds": client.token_lifetime,  # 30 minutes in seconds
        }

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        response = await self.fetch_json(
            url=client_url, method="POST", data=payload, headers=headers
        )
        if not response.get("clientId"):
            raise exceptions.SetupError("Failed creating client ID!")

        client_id = response.get("clientId")
        integration_id = response.get("id")

        secret_url = f"{jamf_url}/api/v1/api-integrations/{integration_id}/client-credentials"
        secret_response = await self.fetch_json(url=secret_url, method="POST", headers=headers)

        if not secret_response.get("clientSecret"):
            raise exceptions.SetupError(f"Failed creating client secret for {client_id}")

        client_secret = secret_response.get("clientSecret")
        return client_id, client_secret
