import asyncio
import json
import ssl
from typing import Any
from urllib.parse import urlencode

import httpx
import truststore

from ..core.exceptions import APIResponseError, PatcherError
from ..core.logger import LogMe
from ..core.models.jamf import ApiClientModel, ApiRoleModel


class HTTPClient:
    def __init__(self, max_concurrency: int = 5):
        """
        The HTTPClient class controls concurrency settings and secure connections for *all* API calls.

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
        self.log.debug(f"HTTPClient initialized with max_concurrency: {max_concurrency}")

    def set_concurrency(self, value: int) -> None:
        """
        Set the maximum concurrency level for outbound API requests, with validation.

        Read access is via the :attr:`max_concurrency` attribute directly;
        this method exists specifically for validated writes. It is recommended
        to keep the value at no more than 5 to avoid overloading Jamf. See
        the class docstring for the upstream guidance.

        :param value: The new maximum concurrency level.
        :type value: int
        :raises PatcherError: If ``value`` is less than 1.
        """
        if value < 1:
            raise PatcherError("Concurrency level must be at least 1.")
        self.max_concurrency = value

    @property
    def http(self) -> httpx.AsyncClient:
        """
        Lazily-constructed :class:`httpx.AsyncClient` bound to this HTTPClient instance.

        First access constructs the client; subsequent accesses return the same
        instance. Call :meth:`aclose` to release the underlying connection pool
        when this HTTPClient is no longer needed. The CLI doesn't strictly
        need to call ``aclose`` (process exit reclaims resources), but library
        consumers should for clean shutdown.

        :return: The shared ``httpx.AsyncClient`` for this instance.
        :rtype: httpx.AsyncClient

        .. note::
            Not thread-safe. HTTPClient is intended for single-event-loop use.
            ``max_connections`` is bound to ``self.max_concurrency`` so the same
            ceiling that gates ``self.semaphore`` also applies at the HTTP layer.
        """
        if self._http_client is None:
            # truststore.SSLContext bridges Python's ssl module to the OS's
            # native trust store. Corporate CAs installed via MDM are trusted
            # automatically; no certifi-modification dance required.
            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=self.max_concurrency),
                follow_redirects=True,
                verify=ctx,
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
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
    ) -> str:
        """
        Fetch the body of a URL as text via httpx.

        Translates httpx-native errors to Patcher's :class:`APIResponseError`
        so callers see the same exception contract as the existing
        :meth:`fetch_json` path, notably the ``not_found=True`` flag on 404
        responses, which :meth:`patcher.clients.installomator.InstallomatorClient.match`
        uses to short-circuit gracefully.

        :param url: The URL to fetch.
        :type url: str
        :param headers: Optional request headers. If omitted, only httpx
            defaults are sent.
        :type headers: dict[str, str] | None
        :param params: Optional query parameters. Accepts a mapping for
            unique keys, or a list of ``(key, value)`` tuples when the same
            key needs to repeat (e.g., ``columns-to-export`` on the Jamf
            CSV export endpoint). Forwarded to httpx, which handles URL
            encoding.
        :type params: dict[str, Any] | list[tuple[str, Any]] | None
        :return: The response body as a string.
        :rtype: str
        :raises APIResponseError: If the response is non-2xx, or if a
            network-level error (connect, DNS, timeout) prevents the
            request from completing. ``not_found=True`` is set on 404.
        """
        self.log.debug(f"Fetching text from {url}")
        try:
            async with self.semaphore:
                response = await self.http.get(url, headers=headers, params=params)
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

    def _raise_for_status(self, status_code: int, response_json: dict | None) -> None:
        """
        Raise :class:`APIResponseError` if ``status_code`` is non-2xx.

        2xx is a no-op (control returns to the caller, which uses
        ``response_json`` directly). 404 carries ``not_found=True`` so callers
        can distinguish missing-resource from other client errors. 4xx, 5xx,
        and anything outside 200-599 each get a distinct error message.

        Pulls a human-readable ``error`` field from the JSON body's
        ``"errors"`` key when present; otherwise reports ``"No details"``.
        """
        self.log.debug(f"Parsing API response. (status code: {status_code})")

        if 200 <= status_code < 300:
            self.log.info("API call successful.")
            return

        error_message = (
            response_json.get("errors", "Unknown error") if response_json else "No details"
        )
        if status_code == 404:
            raise APIResponseError(
                "Requested resource was not found.",
                status_code=status_code,
                error=error_message,
                not_found=True,
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
        on the ``Content-Type`` header of the merged request headers; the
        same routing logic the prior curl-based implementation used. Non-2xx
        responses are translated via :meth:`_raise_for_status` into
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
        self._raise_for_status(response.status_code, response_json)
        return response_json

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
        :param headers: Optional headers to include in the request. Defaults to ``self.headers`` via the :meth:`~patcher.clients.__init__.fetch_json` method.
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
        :param jamf_url: Jamf Server URL (See :attr:`~patcher.core.models.jamf.JamfCredentials.server`).
        :type jamf_url: str
        :returns: The BasicToken string.
        :rtype: str
        :raises APIResponseError: If the call is unauthorized, unsuccessful, or the response body doesn't contain a ``token`` field.
        """
        self.log.debug("Attempting to retrieve Basic Token with provided credentials.")
        token_url = f"{jamf_url}/api/v1/auth/token"

        try:
            async with self.semaphore:
                response = await self.http.post(
                    token_url,
                    auth=(username, password),
                    headers={"accept": "application/json"},
                )
        except httpx.RequestError as e:
            raise APIResponseError(
                "Network error fetching basic token",
                username=username,
                url=jamf_url,
                error_msg=str(e),
            )

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise APIResponseError(
                "Failed parsing basic token response",
                username=username,
                url=jamf_url,
                status_code=response.status_code,
                error_msg=str(e),
            )

        if response.is_success and data and "token" in data:
            self.log.info("Basic Token retrieved successfully.")
            return data["token"]

        raise APIResponseError(
            "Unable to retrieve basic token with provided username and password",
            username=username,
            url=jamf_url,
            status_code=response.status_code,
        )

    async def create_roles(self, token: str, jamf_url: str) -> bool:
        """
        Creates the necessary API roles using the provided basic token.

        .. seealso::
            :class:`~patcher.core.models.jamf.ApiRoleModel`

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
            :class:`~patcher.core.models.jamf.ApiClientModel`

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
