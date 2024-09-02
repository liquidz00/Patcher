import asyncio
import ssl
from pathlib import Path
from typing import Dict, List, Optional, Union

import aiohttp

from ..utils import logger


class SSLContextManager:
    """
    Manages SSL context for secure connections, with support custom Certificate Authority (CA) files.

    This class is part of Patcher's backend and helps ensure that any communication made is secure. If
    you have a custom CA file (for example, from your organization), this manager will merge it with the system's
    default CA certificates for enhanced SSL verification.

    :param custom_ca_file: Path to a custom CA file. If not provided, the system's default CA certificates are used.
    :type custom_ca_file: Optional[Union[str, pathlib.Path]] = None
    """

    def __init__(self, custom_ca_file: Optional[Union[str, Path]] = None):
        self.custom_ca_file = custom_ca_file
        self._merged_cafile_path = (
            Path.home() / "Library" / "Application Support" / "Patcher" / "merged_cafile.pem"
        )

    def create_ssl_context(self) -> ssl.SSLContext:
        """
        Creates an SSL context object, optionally including a custom CA file.

        This method generates an SSL context that is used by Patcher to securely connect
        to servers. If you’ve specified a custom CA file when running the tool, it will be
        incorporated into the SSL context, providing additional security.

        :return: An SSL context ready for secure connections.
        :rtype: ssl.SSLContext
        """

        context = ssl.create_default_context()
        if self.custom_ca_file:
            merged_cafile_path = self._get_merged_cafile_path()
            context.load_verify_locations(cafile=str(merged_cafile_path))
        return context

    def _get_merged_cafile_path(self) -> Path:
        """
        Retrieves the path to the merged CA file for SSL verification.

        :return: Path to the merged CA file used by Patcher.
        :rtype: pathlib.Path
        """
        self._merge_ca_files()
        return self._merged_cafile_path

    def _merge_ca_files(self) -> None:
        """
        Merges the system’s default CA certificates with the custom CA file, if provided.

        This method is called when Patcher needs to create a secure SSL context. It combines
        the custom CA file with the default system certificates, ensuring that both are used
        for SSL verification.

        .. note::
            If no custom CA file is provided, or if the merged file already exists, this method will not make any changes.

        :raises FileNotFoundError: If the default or custom CA file cannot be found.
        :example:

        .. code-block:: console

            $ patcherctl --custom-ca-file '/path/to/cafile.pem'

        """
        if not self.custom_ca_file or self._merged_cafile_path.exists():
            return

        default_cafile = ssl.get_default_verify_paths().cafile

        with open(default_cafile, "r") as default_file:
            default_content = default_file.read()

        with open(self.custom_ca_file, "r") as custom_file:
            custom_content = custom_file.read()

        merged_content = default_content + "\n" + custom_content

        self._merged_cafile_path.parent.mkdir(parents=True, exist_ok=True)

        # Write merged CA file content to persistent location
        with open(self._merged_cafile_path, "w") as merged_file:
            merged_file.write(merged_content)


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

    :param custom_ca_file: Path to a custom CA file for SSL verification, if needed.
    :type custom_ca_file: Optional[str]

    """

    def __init__(
        self,
        max_concurrency: int = 5,
        custom_ca_file: Optional[str] = None,
    ):
        self.max_concurrency = max_concurrency
        self.ssl_context_manager = SSLContextManager(custom_ca_file=custom_ca_file)
        self.ssl_context = self.ssl_context_manager.create_ssl_context()
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.default_headers = {"accept": "application/json"}
        self.session: Optional[aiohttp.ClientSession] = None
        self.log = logger.LogMe(self.__class__.__name__)

    @property
    def concurrency(self) -> int:
        """
        Gets the current concurrency setting used by Patcher.

        :return: The maximum number of concurrent API requests that can be made.
        :rtype: int
        """
        return self.max_concurrency

    def create_session(self) -> aiohttp.ClientSession:
        """
        Creates an HTTP session for making API requests.

        This method is primarily in place to prevent repeated code (DRY principle).

        :return: An HTTP session prepped for API requests.
        :rtype: aiohttp.ClientSession
        """
        return aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=self.max_concurrency))

    def set_max_concurrency(self, concurrency: int):
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
            raise ValueError("Concurrency level must be at least 1. ")
        self.max_concurrency = concurrency

    async def fetch_json(
        self, url: str, headers: Optional[Dict[str, str]] = None
    ) -> Optional[Dict]:
        """
        Fetches JSON data from a specified URL asynchronously.

        :param url: URL to fetch the JSON data from.
        :type url: str
        :param headers:
        :type headers: Optional[Dict[str, str]]
        :return: JSON data as a dictionary or None if an error occurs.
        :rtype: Optional[Dict]
        """
        if self.session is None:
            self.session = self.create_session()

        final_headers = headers if headers else self.default_headers

        self.log.debug(f"Fetching JSON data from URL: {url}")
        try:
            async with self.semaphore:
                async with self.session.get(
                    url, ssl=self.ssl_context, headers=final_headers
                ) as response:
                    response.raise_for_status()
                    json_data = await response.json()
                    self.log.info(f"Successfully fetched JSON data from {url}")
                    return json_data
        except aiohttp.ClientResponseError as e:
            self.log.error(f"Received a client error while fetching JSON from {url}: {e}")
        except Exception as e:
            self.log.error(f"Error fetching JSON: {e}")
        return None

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
        if self.session is None:
            self.session = self.create_session()

        for i in range(0, len(urls), self.max_concurrency):
            batch = urls[i : i + self.max_concurrency]
            tasks = [self.fetch_json(url, headers=headers) for url in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
        return results

    async def close(self):
        """
        Closes HTTP session(s) used by Patcher.

        Once Patcher has finished making API requests, this method is called to
        automatically close any session that remained open. This helps free up system
        resources and maintain a clean operating environment.
        """
        if self.session and not self.session.closed:
            await self.session.close()
            self.log.info("Client session successfully closed.")
