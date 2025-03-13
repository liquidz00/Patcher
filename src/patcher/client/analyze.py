import pickle
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

import pandas as pd

from ..models.patch import PatchTitle
from ..utils.data_manager import DataManager
from ..utils.exceptions import PatcherError
from ..utils.logger import LogMe


class BaseEnum(Enum):
    """Base class for Enum extensions with reusable CLI parsing."""

    @classmethod
    def from_cli(cls, value: str) -> "BaseEnum":
        """
        Maps CLI-friendly inputs (e.g., '--most-installed', '--release-frequency') to Enum values.

        :param value: CLI-friendly string.
        :type value: :py:class:`str`
        :return: Corresponding Enum value
        :rtype: :class:`~patcher.client.analyze.FilterCriteria` | :class:`~patcher.client.analyze.TrendCriteria`
        :raises PatcherError: If the input is invalid
        """
        formatted_value = value.replace("-", "_")
        try:
            return cls(formatted_value)
        except ValueError:
            valid_values = ", ".join(c.value.replace("_", "-") for c in cls)
            raise PatcherError(
                "Invalid criteria provided.", received=value, supported_values=valid_values
            )


class FilterCriteria(BaseEnum):
    """Enumeration for filtering criteria used in patch data analysis."""

    MOST_INSTALLED = "most_installed"
    LEAST_INSTALLED = "least_installed"
    OLDEST_LEAST_COMPLETE = "oldest_least_complete"
    BELOW_THRESHOLD = "below_threshold"
    HIGH_MISSING = "high_missing"
    RECENT_RELEASE = "recent_release"
    ZERO_COMPLETION = "zero_completion"
    TOP_PERFORMERS = "top_performers"
    INSTALLOMATOR = "installomator"


class TrendCriteria(BaseEnum):
    """Enumeration for trend analysis criteria."""

    PATCH_ADOPTION = "patch_adoption"
    RELEASE_FREQUENCY = "release_frequency"
    COMPLETION_TRENDS = "completion_trends"
    # HOST_TRENDS = "host_trends"  # Adding for later


class Analyzer:
    def __init__(
        self,
        data_manager: DataManager,
        excel_path: Optional[Union[Path, str]] = None,
    ):
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

    def _combine_datasets(self, datasets: List[Union[pd.DataFrame, Path, str]]) -> pd.DataFrame:
        """Combines multiple datasets into a single DataFrame."""
        dataframes = []
        for dataset in datasets:
            if isinstance(dataset, pd.DataFrame):
                dataframes.append(dataset)
            elif isinstance(dataset, (Path, str)):
                self.log.debug(f"Loading dataset from: {dataset}")
                file_path = Path(dataset)
                if file_path.suffix == ".pkl":
                    with open(file_path, "rb") as f:
                        df = pickle.load(f)
                elif file_path.suffix in [".xlsx", ".xls"]:
                    df = self.initialize_dataframe(dataset)

            df.columns = [col.lower().replace(" ", "_") for col in df.columns]
            if "released" in df.columns:
                df["released"] = pd.to_datetime(df["released"], format="%b %d %Y")
            dataframes.append(df)

        combined_df = pd.concat(dataframes, ignore_index=True)
        self.log.info(f"Combined {len(dataframes)} datasets into a single DataFrame.")
        return combined_df

    def initialize_dataframe(self, excel_path: Union[Path, str]) -> pd.DataFrame:
        """
        Initializes a DataFrame by reading the Excel file from the provided path.

        :param excel_path: The path to the Excel file, either as a string or a :py:class:`~pathlib.Path` object.
        :type excel_path: :py:obj:`~typing.Union` [:py:obj:`~pathlib.Path` | :py:class:`str`]
        :return: A pandas DataFrame loaded from the Excel file.
        :rtype: `pandas.DataFrame <https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html>`_
        :raises PatcherError: If the passed ``excel_file`` could not be validated (does not exist, or is not a file).
        :raises PatcherError: If the excel file could not be read, if the file is empty, or if the file could not be parsed properly.
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
            raise PatcherError(
                "Unable to read CSV file due to permissions issues.",
                path=excel_path,
                error_msg=str(e),
            )
        except pd.errors.EmptyDataError as e:
            self.log.error(f"The file at {excel_path} is empty. Details: {e}")
            raise PatcherError(
                "The Excel file provided is empty.",
                path=excel_path,
                error_msg=str(e),
            )
        except pd.errors.ParserError as e:
            self.log.error(f"Failed to parse the Excel file at {excel_path}. Details: {e}")
            raise PatcherError(
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
                - 'installomator': Titles that have Installomator labels. See :ref:`Installomator <installomator>`

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
            FilterCriteria.INSTALLOMATOR: lambda: [pt for pt in titles if pt.install_label != []],
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

    def timelapse(
        self,
        criteria: TrendCriteria,
        datasets: Optional[List[Union[Path, str, pd.DataFrame]]] = None,
        sort_by: Optional[str] = None,
        ascending: bool = True,
    ) -> pd.DataFrame:
        """
        Analyzes trends across multiple datasets based on specified criteria.

        :param criteria: The trend analysis criteria to use.
        :type criteria: :class:`~patcher.client.analyze.TrendCriteria`
        :param datasets: A list of DataFrames or file paths to analyze. If None, uses cached data.
        :type datasets: :py:obj:`~typing.Optional` [:py:obj:`~typing.List`]
        :param sort_by: A column to sort the results by.
        :type sort_by: :py:obj:`~typing.Optional` [:py:class:`str`]
        :param ascending: Sorting order (ascending if True, descending if False).
        :type ascending: :py:class:`bool`
        :return: A DataFrame with the trend analysis results.
        :rtype: `pandas.DataFrame <https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html>`_
        :raises PatcherError: If criteria is invalid or data loading fails.
        """
        if datasets is None:
            datasets = self.data_manager.get_cached_files()

        if len(datasets) < 2:
            raise PatcherError(
                "Insufficient cache data to analyze trends.", amount_found=len(datasets)
            )

        combined_df = self._combine_datasets(datasets)

        trend_criteria: Dict[TrendCriteria, Callable[[], pd.DataFrame]] = {
            TrendCriteria.PATCH_ADOPTION: lambda: combined_df.groupby("title", as_index=False)
            .agg(
                average_completion=("completion_percent", "mean"),
                recent_release=("released", "max"),
            )
            .rename(
                columns={
                    "title": "Title",
                    "average_completion": "Average Completion",
                    "recent_release": "Most Recent Release",
                }
            )
            .assign(
                **{
                    "Most Recent Release": lambda df: df["Most Recent Release"].dt.strftime(
                        "%Y-%m-%d"
                    ),
                    "Average Completion": lambda df: df["Average Completion"].apply(
                        lambda x: f"{x:.2f}%"
                    ),
                }
            ),
            TrendCriteria.RELEASE_FREQUENCY: lambda: combined_df.groupby("title", as_index=False)
            .agg(release_count=("released", "nunique"))
            .rename(columns={"title": "Title", "release_count": "Release Count"}),
            TrendCriteria.COMPLETION_TRENDS: lambda: combined_df.groupby(
                ["released", "title"], as_index=False
            )
            .agg(average_completion=("completion_percent", "mean"))
            .rename(
                columns={
                    "title": "Title",
                    "average_completion": "Average Completion",
                    "released": "Release Date",
                }
            )
            .assign(
                **{
                    "Release Date": lambda df: df["Release Date"].dt.strftime("%Y-%m-%d"),
                    "Average Completion": lambda df: df["Average Completion"].apply(
                        lambda x: f"{x:.2f}%"
                    ),
                }
            ),
        }

        if criteria not in trend_criteria:
            raise PatcherError(
                "Invalid criteria passed.",
                received=criteria,
                supported_criteria=(", ".join(c.value for c in TrendCriteria)),
            )

        trend_df = trend_criteria[criteria]()

        if sort_by:
            if sort_by not in trend_df.columns:
                raise PatcherError(
                    "Invalid sorting provided.",
                    received=sort_by,
                    expected=(", ".join(trend_df.columns)),
                )
            trend_df = trend_df.sort_values(by=sort_by, ascending=ascending)

        self.log.info(f"Performed '{criteria.value}' trend analysis successfully.")
        return trend_df
