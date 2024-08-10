import asyncio
from datetime import datetime, timedelta
from typing import List

import aiohttp

from ..models.patch import PatchTitle
from ..utils import exceptions, logger


class Analyzer:
    def __init__(self, titles: List[PatchTitle], labels: List[str]):
        self.patch_titles = titles
        self.labels = labels
        self.log = logger.LogMe(self.__class__.__name__)

    def analyze(self):
        for patch in self.patch_titles:
            if patch.title in self.labels:
                patch.installomator = True

    @staticmethod
    def format_table(data, headers=None):
        if headers:
            data = [headers] + data

        # Calculate maximum width for each column
        column_widths = [max(len(str(item)) for item in column) for column in zip(*data)]

        # Create a format string with the calculated column widths
        format_string = " | ".join([f"{{:<{width}}}" for width in column_widths])

        # Generate the table rows using the format string
        table = [format_string.format(*row) for row in data]

        # Optionally add a separator after headers
        if headers:
            header_separator = "-+-".join("-" * width for width in column_widths)
            table.insert(1, header_separator)

        return "\n".join(table)

    async def fetch_cve_data(
        self, session: aiohttp.ClientSession, title: str, severity: str
    ) -> List[str]:
        url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
        end_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.%f")[
            :-3
        ] + "Z"

        params = {
            "keywordSearch": title,
            "resultsPerPage": 20,
            "startIndex": 0,
            "pubStartDate": start_date,
            "pubEndDate": end_date,
            "cvssV3Severity": severity,
        }

        try:
            async with session.get(url=url, params=params) as resp:
                resp.raise_for_status()
                cves = await resp.json()
                cve_ids = [cve["cve"]["id"] for cve in cves.get("vulnerabilities", [])]
        except aiohttp.ClientResponseError as e:
            self.log.error(f"Error fetching {severity} CVE data for {title}: {e}")
            raise exceptions.PatcherError(message=f"Error fetching {severity} CVE data for {title}")

        return cve_ids

    async def fetch_criticals(self, title: str) -> List[str]:
        async with aiohttp.ClientSession() as session:
            high_cves = await self.fetch_cve_data(session=session, title=title, severity="HIGH")
            critical_cves = await self.fetch_cve_data(
                session=session, title=title, severity="CRITICAL"
            )
            return high_cves + critical_cves

    async def print_table(self):
        tasks = []
        for patch in self.patch_titles:
            if patch.installomator:
                tasks.append(self.fetch_criticals(patch.title))

        cve_results = await asyncio.gather(*tasks)

        data = []
        for i, patch in enumerate(self.patch_titles):
            if patch.installomator:
                cve_id_str = ", ".join(cve_results[i] if cve_results[i] else "None")
                data.append([patch.title, "Yes", patch.completion_percent, cve_id_str])

        headers = [
            "Software Title",
            "Installomator Support",
            "Completion Percentage",
            "High/Critical CVEs",
        ]
        table = self.format_table(data, headers)
        print(table)
