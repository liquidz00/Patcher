from pathlib import Path
from typing import AnyStr, List, Optional

import pandas as pd

from ..models.patch import PatchTitle
from ..utils import database, exceptions, logger
from .api_client import ApiClient
from .config_manager import ConfigManager
from .token_manager import TokenManager

# TODO
# 2. Iron out accurate installomator labels
# 3. Analysis based on PatchTitle criteria (completion percent, release date, etc.)


class Analyzer:
    def __init__(self, config: ConfigManager, concurrency: int, custom_ca_file: Optional[str]):
        self.log = logger.LogMe(self.__class__.__name__)

        self.config = config
        self.token_manager = TokenManager(config)
        self.api = ApiClient(config=config, concurrency=concurrency, custom_ca_file=custom_ca_file)
        self.jamf_client = config.attach_client()
        if not self.jamf_client:
            self.log.error("Invalid JamfClient configuration detected!")
            raise ValueError("Invalid JamfClient configuration detected!")

        self.labels_dir = Path.home() / "Library" / "Application Support" / "Patcher" / ".labels"
        self.db = self.labels_dir.parent / ".patcher.db"

        self.dataframe = pd.DataFrame()
        self.db_agent = database.DBAgent()

        self.patch_titles: List[PatchTitle] = []

    def _check_db(self) -> bool:
        """Checks for the presence of PatchTitles within the Patcher database."""
        return self.db_agent.has_patches

    async def _get_patches(self) -> None:
        policies = await self.api.get_policies()
        if not policies:
            self.log.error("Unable to retrieve PatchTitle IDs for analysis.")
            raise exceptions.PatcherError("Unable to retrieve PatchTitle objects for analysis.")
        patch_titles = await self.api.get_summaries(policy_ids=policies)
        if not patch_titles:
            self.log.error("Unable to retrieve PatchTitle summaries for analysis")
            raise exceptions.PatcherError("Unable to retrieve PatchTitle summaries for analysis.")
        for title in patch_titles:
            self.patch_titles.append(title)

    async def initialize_dataframe(self):
        if not self._check_db():
            self.log.info(f"PatchTitle objects missing from database: {self.db_agent.db_path}")
            await self._get_patches()

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
