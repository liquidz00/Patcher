import asyncio
import json
import subprocess
from typing import Optional, Dict, List
from ..utils import logger, exceptions


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
        self.default_headers = {"accept": "application/json"}
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

    async def execute(self, command: List[str]) -> Optional[Dict]:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            self.log.error(f"Error executing subprocess command: {stderr.decode()}")
            return None
        return json.loads(stdout.decode())

    async def fetch_json(self, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[Dict]:
        final_headers = headers if headers else self.default_headers
        header_string = " ".join([f"-H '{k}: {v}'" for k, v in final_headers.items()])
        command = ["/usr/bin/curl", "-s", url, header_string]
        async with self.semaphore:
            return await self.execute(command)

    async def fetch_batch(self, urls: List[str], headers: Optional[Dict[str, str]] = None) -> List[Optional[Dict]]:
        results = []
        for i in range(0, len(urls), self.max_concurrency):
            batch = urls[i:i + self.max_concurrency]
            tasks = [self.fetch_json(url, headers=headers) for url in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
        return results
