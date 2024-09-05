from pathlib import Path
from typing import List, Optional, Callable

import pandas as pd

from ..models.patch import PatchTitle
from ..utils import database, exceptions, logger
from ..utils.wrappers import check_token
from .api_client import ApiClient
from .config_manager import ConfigManager
from .token_manager import TokenManager

# TODO
# 3. Analysis based on PatchTitle criteria (completion percent, release date, etc.)


class Analyzer:
    def __init__(self, config: ConfigManager, token_manager: TokenManager, api_client: ApiClient):
        self.log = logger.LogMe(self.__class__.__name__)
        self.config = config
        self.token_manager = token_manager
        self.api = api_client
        self.jamf_client = config.attach_client()
        if not self.jamf_client:
            self.log.error("Invalid JamfClient configuration detected!")
            raise ValueError("Invalid JamfClient configuration detected!")
        self.db_agent = database.DBAgent()
        self.patch_titles: List[PatchTitle] = []
        self.dataframe = pd.DataFrame()

    def _check_db(self) -> bool:
        """Checks for the presence of PatchTitles within the Patcher database."""
        return self.db_agent.has_patches

    async def initialize_dataframe(self):
        """Initializes the dataframe by loading data from the SQLite database."""
        if not self._check_db():
            self.log.info(f"PatchTitle objects missing from database: {self.db_agent.db_path}")
            await self._get_patches()

        patch_df = self.db_agent.load_dataframe("patch_titles")
        app_df = self.db_agent.load_dataframe("app_titles")
        label_df = self.db_agent.load_dataframe("labels")

        if patch_df is not None and app_df is not None:
            self.dataframe = pd.merge(
                app_df, patch_df, left_on="id", right_on="app_title_id", how="left"
            )

        if label_df is not None and not self.dataframe.empty:
            self.dataframe = pd.merge(
                self.dataframe, label_df, left_on="id", right_on="app_title_id", how="left"
            )

        if self.dataframe.empty:
            self.log.warning("Dataframe is empty! No data available for analysis.")

    @check_token
    async def _get_patches(self) -> None:
        policies = await self.api.get_policies()
        if not policies:
            self.log.error("Unable to retrieve PatchTitle IDs for analysis.")
            raise exceptions.PolicyFetchError(url=self.api.jamf_url)
        patch_titles = await self.api.get_summaries(policy_ids=policies)
        if not patch_titles:
            self.log.error("Unable to retrieve PatchTitle summaries for analysis")
            raise exceptions.SummaryFetchError(url=self.api.jamf_url)
        for title in patch_titles:
            self.patch_titles.append(title)

    @staticmethod
    def format_table(data: List[List[str]], headers: Optional[List[str]] = None) -> str:
        """
        Formats the data passed into a table for CLI output.

        :param data: The data to display in the table.
        :type data: List[List[str]]
        :param headers: Header names for the columns of the tables.
        :type headers: Optional[List[str]]
        :return: The formatted table as a string.
        :rtype: str
        """
        if headers:
            data = [headers] + data

        column_widths = [max(len(str(item)) for item in column) for column in zip(*data)]
        format_string = " | ".join([f"{{:<{width}}}" for width in column_widths])
        table = [format_string.format(*row) for row in data]

        if headers:
            header_separator = "-+-".join("-" * width for width in column_widths)
            table.insert(1, header_separator)

        return "\n".join(table)

    @classmethod
    async def print_table(
        cls,
        patch_titles: List[PatchTitle],
        criteria: str,
    ) -> str:
        # TODO
        pass

    @classmethod
    def filter_titles(
        cls,
        patch_titles: List[PatchTitle],
        criteria: str,
        threshold: Optional[float] = 70.0,
        top_n: Optional[int] = 3,
    ) -> List[PatchTitle]:
        """
        Filters and sorts PatchTitle objects based on specified criteria.

        :param patch_titles: A list of PatchTitle objects.
        :type patch_titles: List[PatchTitle]
        :param criteria: The criteria to filter and sort by. Options are:
            - 'most_installed': Returns the top N most installed software by total_hosts.
            - 'least_installed': Returns the top N least installed software by total_hosts.
            - 'oldest_least_complete': Returns the top N oldest patches with the least completion percent.
            - 'below_threshold': Returns patches below a certain completion percentage.
        :type criteria: str
        :param threshold: The threshold for filtering completion percentages, default is 70.0.
        :type threshold: Optional[float]
        :param top_n: The number of results to return, default is 3.
        :type top_n: Optional[int]
        :return: A list of filtered and sorted PatchTitle objects.
        :rtype: List[PatchTitle]
        """
        sort_criteria: dict[str, Callable[[List[PatchTitle]], List[PatchTitle]]] = {
            "most_installed": lambda patches: sorted(
                patches, key=lambda pt: pt.total_hosts, reverse=True
            )[:top_n],
            "least_installed": lambda patches: sorted(patches, key=lambda pt: pt.total_hosts)[
                :top_n
            ],
            "oldest_least_complete": lambda patches: sorted(
                patches, key=lambda pt: (pt.released, pt.completion_percent)
            )[:top_n],
            "below_threshold": lambda patches: sorted(
                [pt for pt in patches if pt.completion_percent < threshold],
                key=lambda pt: pt.completion_percent,
            ),
        }

        # Check for valid criteria
        if criteria not in sort_criteria:
            raise ValueError(
                f"Invalid criteria '{criteria}'. Supported criteria: {', '.join(sort_criteria.keys())}."
            )

        # Apply sorting/filtering strategy
        return sort_criteria[criteria](patch_titles)
