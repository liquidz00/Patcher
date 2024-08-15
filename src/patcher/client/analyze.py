import os
import sqlite3
from datetime import datetime, timedelta
from typing import AnyStr, Dict, List, Tuple

import aiohttp
import pandas as pd
from rapidfuzz import process

from ..models.patch import PatchTitle
from ..utils import exceptions, logger

# TODO
# 2. Iron out accurate installomator labels
# 3. Analysis based on PatchTitle criteria (completion percent, release date, etc.)
# 4. Jamf app installer support?
# 5. Iron out CVE data gathering and formatting

DATABASE = os.path.expanduser("~/Library/Application Support/Patcher/.patcher.db")
LABELS = os.path.expanduser("~/Library/Application Support/Patcher/installomator_labels")


class Analyzer:
    def __init__(self, titles: List[PatchTitle]):
        self.patch_titles = titles
        self.labels = self._fetch()
        self.dataframe = pd.DataFrame()
        self.log = logger.LogMe(self.__class__.__name__)

    async def initialize_dataframe(self):
        records = []

        for patch_title in self.patch_titles:
            cves = await self.fetch_criticals(patch_title.title)
            label, _ = self._match(patch_title.title)
            record = {
                "Software Title": patch_title.title,
                "Installomator Label": label,
                "CVE Count": len(cves),
                "CVE Details": ", ".join(cves) if cves else "None",
                "Completion Percentage": patch_title.completion_percent,
            }
            records.append(record)

        self.dataframe = pd.DataFrame(records)

        conn = sqlite3.connect(DATABASE)
        self.dataframe.to_sql("software_analysis", conn, if_exists="replace", index=False)
        conn.close()

    def _get_titles(self):
        return [patch.title for patch in self.patch_titles]

    # Get installomator labels for titles
    @staticmethod
    def _fetch() -> Dict[str, str]:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        c.execute("SELECT application_title, installomator_label FROM labels")
        results = c.fetchall()
        c.close()

        return {title: label for title, label in results}

    def _match(self, title: str) -> Tuple[str, str]:
        threshold = 90
        matched_title, score, _ = process.extractOne(
            title, self.labels.keys(), score_cutoff=threshold
        )
        if matched_title:
            return matched_title, self.labels.get(matched_title)
        return title, "Unsupported"

    def map(self, patch_titles: List[PatchTitle]) -> Dict[str, str]:
        mapped_titles = {}

        for title in patch_titles:
            matched_title, matched_label = self._match(title.title)
            mapped_titles[title.title] = matched_label

        return mapped_titles

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

        headers = {"apiKey": "c12c82dd-2205-425c-893a-407a583184a0"}

        try:
            async with session.get(url=url, params=params, headers=headers) as resp:
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

    async def print_table(self) -> AnyStr:
        if self.dataframe.empty:
            await self.initialize_dataframe()

        data = self.dataframe.copy()
        headers = [
            "Software Title",
            "Installomator Label",
            "CVE Count",
            "CVE Details",
            "Completion Percentage",
        ]
        table_data = data[headers].values.tolist()

        table = self.format_table(table_data, headers)
        return table

    async def below_threshold(self, threshold: int) -> AnyStr:
        if self.dataframe.empty:
            await self.initialize_dataframe()

        filtered_df = self.dataframe[self.dataframe["Completion Percentage"] < threshold]

        if filtered_df.empty:
            return f"No titles found below the {threshold}% completion threshold."

        data = filtered_df[
            [
                "Software Title",
                "Installomator Label",
                "CVE Count",
                "CVE Details",
                "Completion Percentage",
            ]
        ]
        table_data = data.values.tolist()
        headers = data.columns.tolist()

        table = self.format_table(table_data, headers)
        return table
