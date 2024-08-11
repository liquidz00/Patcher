import asyncio
from typing import Dict, List, Optional
from urllib.parse import quote

import aiohttp

from ..models.patch import PatchTitle
from ..utils import logger

# TODO
# 2. Iron out accurate installomator labels
# 3. Pandas dataframe analysis based on PatchTitle criteria (completion percent, release date, etc.)
# 4. Jamf app installer support?
# 5. Iron out CVE data gathering and formatting


class Analyzer:
    def __init__(self, titles: List[PatchTitle], labels: List[str]):
        self.patch_titles = titles
        self.labels = labels
        self.log = logger.LogMe(self.__class__.__name__)

    def _get_titles(self):
        return [patch.title for patch in self.patch_titles]

    # Get installomator labels for titles
    async def get_labels(self, session: aiohttp.ClientSession, patch_titles: List[str]):
        tasks = []
        for title in patch_titles:
            encoded_title = quote(title)
            url = f"http://69.164.208.43:5000/api/get_label?app_title={encoded_title}"
            tasks.append(self.fetch_label(session, url, title))

        responses = await asyncio.gather(*tasks)
        return responses

    async def fetch_label(
        self, session: aiohttp.ClientSession, url: str, title: str
    ) -> Optional[Dict[str, str]]:
        try:
            async with session.get(url, ssl=False) as resp:  # Only for testing, change before prod
                resp.raise_for_status()
                data = await resp.json()
                return {
                    "Software Title": title,
                    "Installomator Label": data.get("installomator_label", "Unknown"),
                    "Completion Percentage": "N/A",  # Will be set below
                }
        except aiohttp.ClientError as e:
            self.log.error(f"Error fetching label for {title}: {e}")
            return None

    @staticmethod
    def format_table(data, headers=None):
        if headers:
            data = [headers] + data

        column_widths = [max(len(str(item)) for item in column) for column in zip(*data)]
        format_string = " | ".join([f"{{:<{width}}}" for width in column_widths])
        table = [format_string.format(*row) for row in data]

        if headers:
            header_separator = "-+-".join("-" * width for width in column_widths)
            table.insert(1, header_separator)

        return "\n".join(table)

    async def print_table(self):
        async with aiohttp.ClientSession() as session:
            titles = self._get_titles()
            label_data = await self.get_labels(session, titles)

            # Update label_data with completion percentage from PatchTitle
            for i, item in enumerate(label_data):
                item["Completion Percentage"] = f"{self.patch_titles[i].completion_percent}%"

            data = [
                [item["Software Title"], item["Installomator Label"], item["Completion Percentage"]]
                for item in label_data
            ]
            headers = ["Software Title", "Installomator Label", "Completion Percentage"]
            table = self.format_table(data, headers)
            print(table)

    # async def fetch_cve_data(
    #     self, session: aiohttp.ClientSession, title: str, severity: str
    # ) -> List[str]:
    #     url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    #     end_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    #     start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.%f")[
    #         :-3
    #     ] + "Z"
    #
    #     params = {
    #         "keywordSearch": title,
    #         "resultsPerPage": 20,
    #         "startIndex": 0,
    #         "pubStartDate": start_date,
    #         "pubEndDate": end_date,
    #         "cvssV3Severity": severity,
    #     }
    #
    #     try:
    #         async with session.get(url=url, params=params) as resp:
    #             resp.raise_for_status()
    #             cves = await resp.json()
    #             cve_ids = [cve["cve"]["id"] for cve in cves.get("vulnerabilities", [])]
    #     except aiohttp.ClientResponseError as e:
    #         self.log.error(f"Error fetching {severity} CVE data for {title}: {e}")
    #         raise exceptions.PatcherError(message=f"Error fetching {severity} CVE data for {title}")
    #
    #     return cve_ids
    #
    # async def fetch_criticals(self, title: str) -> List[str]:
    #     async with aiohttp.ClientSession() as session:
    #         high_cves = await self.fetch_cve_data(session=session, title=title, severity="HIGH")
    #         critical_cves = await self.fetch_cve_data(
    #             session=session, title=title, severity="CRITICAL"
    #         )
    #         return high_cves + critical_cves
