from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

import pandas as pd

from ..models.patch import PatchTitle
from ..utils.data_manager import DataManager
from ..utils.exceptions import FetchError, PatcherError
from ..utils.logger import LogMe


class FilterCriteria(Enum):
    """Enumeration for filtering criteria used in patch data analysis."""

    MOST_INSTALLED = "most_installed"
    LEAST_INSTALLED = "least_installed"
    OLDEST_LEAST_COMPLETE = "oldest_least_complete"
    BELOW_THRESHOLD = "below_threshold"
    HIGH_MISSING = "high_missing"
    RECENT_RELEASE = "recent_release"
    ZERO_COMPLETION = "zero_completion"
    TOP_PERFORMERS = "top_performers"

    @classmethod
    def from_cli(cls, value: str) -> "FilterCriteria":
        """
        Maps CLI-friendly inputs (e.g., '--most-installed') to Enum values.

        :param value: CLI-friendly string.
        :type value: :py:class:`str`
        :return: Corresponding Enum value
        :rtype: :class:`~patcher.client.analyze.FilterCriteria`
        :raises PatcherError: If the input is invalid
        """
        formatted_value = value.replace("-", "_")
        try:
            return cls(formatted_value)
        except ValueError:
            raise PatcherError(
                "Invalid FilterCriteria passed.",
                criteria=(", ".join(c.value.replace("_", "-") for c in cls)),
            )


class Analyzer:
    def __init__(self, data_manager: DataManager, excel_path: Optional[Union[Path, str]] = None):
        """
        Performs analysis on patch data retrieved via :class:`~patcher.utils.data_manager.DataManager`.

        ``Analyzer`` class objects are initialized with a :class:`~patcher.utils.data_manager.DataManager` instance and optional Excel file path.

        :param data_manager: The ``DataManager`` instance for retrieving and managing patch data.
        :type data_manager: :class:`~patcher.utils.data_manager.DataManager`
        :param excel_path: Path to the Excel file.
        :type excel_path: :py:obj:`~typing.Union` [:py:obj:`~pathlib.Path` | :py:class:`str`]
        """
        self.log = LogMe(self.__class__.__name__)
        self.data_manager = data_manager
        if excel_path:
            self.df = self.initialize_dataframe(excel_path)
        else:
            self.df = pd.DataFrame([patch.model_dump() for patch in self.data_manager.titles])

    def _validate_path(self, file_path: Union[Path, str]) -> bool:
        """Ensures the file path passed exists and is a file (not a directory)."""
        self.log.debug(f"Validating file path: {file_path}")
        if isinstance(file_path, str):
            file_path = Path(file_path)

        if not file_path.exists():
            self.log.error(f"The specified file at {file_path} does not exist.")
            return False
        if not file_path.is_file():
            self.log.error(f"The specified file {file_path} is not a file.")
            return False

        self.log.info(f"File at {file_path} validated successfully.")
        return True

    def initialize_dataframe(self, excel_path: Union[Path, str]) -> pd.DataFrame:
        """
        Initializes a DataFrame by reading the Excel file from the provided path.

        :param excel_path: The path to the Excel file, either as a string or a :py:class:`~pathlib.Path` object.
        :type excel_path: :py:obj:`~typing.Union` [:py:obj:`~pathlib.Path` | :py:class:`str`]
        :return: A pandas DataFrame loaded from the Excel file.
        :rtype: `pandas.DataFrame <https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html>`_
        :raises PatcherError: If the passed ``excel_file`` could not be validated (does not exist, or is not a file).
        :raises FetchError: If the excel file could not be read, if the file is empty, or if the file could not be parsed properly.
        """
        self.log.debug(f"Attempting to initialize DataFrame from {excel_path}")
        if not self._validate_path(excel_path):
            raise PatcherError("Excel file provided failed validation", file_path=excel_path)

        try:
            df = pd.read_excel(excel_path)
            self.log.info(f"DataFrame successfully initialized from {excel_path}.")
            return df
        except PermissionError as e:
            self.log.error(f"Permission denied when trying to read {excel_path}. Details: {e}")
            raise FetchError(
                "Unable to read CSV file due to permissions issues.",
                path=excel_path,
                error_msg=str(e),
            )
        except pd.errors.EmptyDataError as e:
            self.log.error(f"The file at {excel_path} is empty. Details: {e}")
            raise FetchError(
                "The Excel file provided is empty.",
                path=excel_path,
                error_msg=str(e),
            )
        except pd.errors.ParserError as e:
            self.log.error(f"Failed to parse the Excel file at {excel_path}. Details: {e}")
            raise FetchError(
                "Unable to parse the Excel file properly.",
                path=excel_path,
                error_msg=str(e),
            )

    @staticmethod
    def format_table(data: List[List[str]], headers: Optional[List[str]] = None) -> str:
        """
        Formats the data passed into a table for CLI output.

        :param data: The data to display in the table.
        :type data: :py:obj:`~typing.List` [:py:obj:`~typing.List`]
        :param headers: Header names for the columns of the tables.
        :type headers: :py:obj:`~typing.Optional` [:py:obj:`~typing.List`]
        :return: The formatted table as a string.
        :rtype: :py:class:`str`
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

    def filter_titles(
        self,
        criteria: FilterCriteria,
        threshold: Optional[float] = 70.0,
        top_n: Optional[int] = None,
    ) -> List[PatchTitle]:
        """
        Filters and sorts PatchTitle objects based on specified criteria.

        :param criteria: The criteria to filter and sort by.

                Options include:

                - 'most_installed': Returns the most installed software by total_hosts.
                - 'least_installed': Returns the least installed software by total_hosts.
                - 'oldest_least_complete': Returns the oldest patches with the least completion percent.
                - 'below_threshold': Returns patches below a certain completion percentage.
                - 'high_missing': Titles where missing patches are greater than 50% of total hosts.
                - 'zero_completion': Titles with zero completion percentage.
                - 'top_performers': Titles with completion percentage greater than 90%.

        :type criteria: :class:`~patcher.client.analyze.FilterCriteria`
        :param threshold: The threshold for filtering completion percentages, default is 70.0.
        :type threshold: :py:obj:`~typing.Optional` [:py:class:`float`]
        :param top_n: Number of results to return. If None (default), return all matching results.
        :type top_n: :py:obj:`~typing.Optional` [:py:class:`int`]
        :return: Filtered and sorted list of ``PatchTitle`` objects.
        :rtype: :py:obj:`~typing.List` [:class:`~patcher.models.patch.PatchTitle`]
        """
        self.log.debug(f"Attempting to filter titles by {criteria}.")

        titles = self.data_manager.titles
        sort_criteria: Dict[FilterCriteria, Callable[[], List[PatchTitle]]] = {
            FilterCriteria.MOST_INSTALLED: lambda: sorted(
                titles, key=lambda pt: pt.total_hosts, reverse=True
            ),
            FilterCriteria.LEAST_INSTALLED: lambda: sorted(titles, key=lambda pt: pt.total_hosts),
            FilterCriteria.OLDEST_LEAST_COMPLETE: lambda: sorted(
                titles, key=lambda pt: (pt.released, pt.completion_percent)
            ),
            FilterCriteria.BELOW_THRESHOLD: lambda: sorted(
                [pt for pt in titles if pt.completion_percent < threshold],
                key=lambda pt: pt.completion_percent,
            ),
            FilterCriteria.HIGH_MISSING: lambda: sorted(
                [pt for pt in titles if pt.missing_patch > (pt.total_hosts * 0.5)],
                key=lambda pt: pt.missing_patch,
            ),
            FilterCriteria.RECENT_RELEASE: lambda: sorted(
                [
                    pt
                    for pt in titles
                    if pd.Timestamp(pt.released) >= pd.Timestamp.now() - pd.DateOffset(weeks=1)
                ],
                key=lambda pt: pt.released,
                reverse=True,
            ),
            FilterCriteria.ZERO_COMPLETION: lambda: [
                pt for pt in titles if pt.completion_percent == 0
            ],
            FilterCriteria.TOP_PERFORMERS: lambda: sorted(
                [pt for pt in titles if pt.completion_percent > 90],
                key=lambda pt: pt.completion_percent,
                reverse=True,
            ),
        }

        # Check for valid criteria
        if criteria not in sort_criteria:
            raise PatcherError(
                f"Invalid criteria '{criteria}'",
                supported_criteria=(", ".join(c.value for c in FilterCriteria)),
            )

        # Apply sorting/filtering strategy
        filtered_titles = sort_criteria[criteria]()

        if top_n is not None and len(filtered_titles) > top_n:
            filtered_titles = (
                # All results should show (regardless of top_n) for 'below_threshold' and 'zero_completion'
                filtered_titles[:top_n]
                if criteria not in [FilterCriteria.BELOW_THRESHOLD, FilterCriteria.ZERO_COMPLETION]
                else filtered_titles
            )

        self.log.info(
            f"Filtered {len(filtered_titles)} PatchTitles successfully based on {criteria}"
        )
        return filtered_titles