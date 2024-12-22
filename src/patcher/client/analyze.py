from pathlib import Path
from typing import Callable, List, Optional, Union

import pandas as pd

from ..models.patch import PatchTitle
from ..utils.exceptions import FetchError, PatcherError
from ..utils.logger import LogMe

# TODO
# 3. Analysis based on PatchTitle criteria (completion percent, release date, etc.)


class Analyzer:
    def __init__(self, csv_path: Union[Path, str]):
        self.log = LogMe(self.__class__.__name__)
        self.patch_titles: List[PatchTitle] = []
        self.df = self.initialize_dataframe(csv_path)

    def initialize_dataframe(self, csv_path: Union[Path, str]) -> pd.DataFrame:
        """
        Initializes a DataFrame by reading the CSV file from the provided path.

        :param csv_path: The path to the CSV file, either as a string or a pathlib.Path object.
        :type csv_path: Union[Path, str]
        :return: A pandas DataFrame loaded from the CSV file.
        :rtype: pd.DatFrame
        """
        csv_path = Path(csv_path)

        if not csv_path.exists():
            self.log.error(f"The specified file at {csv_path} does not exist.")
            raise PatcherError("The specified file does not exist.", path=csv_path)
        if not csv_path.is_file():
            self.log.error(f"The specified CSV path {csv_path} is not a file.")
            raise PatcherError("The specified CSV path is not a file.", path=csv_path)

        try:
            df = pd.read_csv(csv_path)
            self.log.info(f"DataFrame successfully initialized from {csv_path}.")
            return df
        except PermissionError as e:
            self.log.error(f"Permission denied when trying to read {csv_path}. Details: {e}")
            raise FetchError(
                "Unable to read CSV file due to permissions issues.", path=csv_path
            ) from e
        except pd.errors.EmptyDataError as e:
            self.log.error(f"The file at {csv_path} is empty. Details: {e}")
            raise FetchError("The CSV file provided is empty.", path=csv_path) from e
        except pd.errors.ParserError as e:
            self.log.error(f"Failed to parse the CSV file at {csv_path}. Details: {e}")
            raise FetchError("Unable to parse the CSV file properly.", path=csv_path) from e

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
            raise PatcherError(
                f"Invalid criteria '{criteria}'",
                supported_criteria=(", ".join(sort_criteria.keys())),
            )

        # Apply sorting/filtering strategy
        return sort_criteria[criteria](patch_titles)
