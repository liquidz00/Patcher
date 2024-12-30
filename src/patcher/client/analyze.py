from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Union

import pandas as pd
from pydantic import ValidationError

from ..models.patch import PatchTitle
from ..utils.exceptions import FetchError, PatcherError
from ..utils.logger import LogMe


class FilterCriteria(Enum):
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
    def __init__(self, excel_path: Union[Path, str]):
        """
        Initializes the Analyzer with the path to an Excel file containing patch data.

        :param excel_path: Path to the Excel file.
        :type excel_path: :py:obj:`~typing.Union` of :py:obj:`~pathlib.Path` | :py:class:`str`
        """
        self.log = LogMe(self.__class__.__name__)
        self.patch_titles: Optional[List[PatchTitle]] = None
        self.df = self.initialize_dataframe(excel_path)
        if self.df is not None:
            self.titles = self._create_titles(self.df)  # Explicitly use setter for validation

    @property
    def titles(self) -> List[PatchTitle]:
        """
        Retrieves the validated list of PatchTitle objects.

        :return: :py:obj:`~typing.List` of validated :class:`~patcher.models.patch.PatchTitle` objects.
        :rtype: :py:obj:`~typing.List` of :class:`~patcher.models.patch.PatchTitle`.
        :raises FetchError: If no valid titles are available.
        """
        if self.patch_titles is None:  # Handle uninitialized state only
            raise FetchError(
                "PatchTitles are not available or no valid titles could be created. "
                "Ensure the Excel file provided is valid and contains the required data."
            )
        return self.patch_titles

    @titles.setter
    def titles(self, value: Iterable[PatchTitle]):
        """
        Validates and sets the PatchTitle objects. Ensures the list is non-empty.

        :param value: The list of PatchTitle objects to validate.
        :type value: :py:obj:`~typing.Iterable` of :class:`~patcher.models.patch.PatchTitle`
        :raises PatcherError: If value is not an iterable object.
        :raises FetchError: If any object in the passed iterable object is not a ``PatchTitle`` object, or if titles could not be validated.
        """
        if not isinstance(value, Iterable):
            raise PatcherError(f"Value {value} must be an iterable of PatchTitle objects.")

        validated_titles = []
        for item in value:
            if not isinstance(item, PatchTitle):
                raise PatcherError(f"Item {item} in list is not of PatchTitle type.")
            validated_titles.append(item)

        if not validated_titles:  # Ensure the list is not empty
            raise FetchError("PatchTitles cannot be set to an empty list.")

        self.patch_titles = validated_titles

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

    def _create_titles(self, df: pd.DataFrame) -> List[PatchTitle]:
        """Creates PatchTitle objects from passed dataframe object."""
        self.log.debug(f"Creating PatchTitle objects from DataFrame with {len(df)} rows.")
        patch_titles = []
        skipped_rows = 0

        for index, row in df.iterrows():
            try:
                patch = PatchTitle(
                    title=row.get("Title"),
                    released=row.get("Released"),
                    hosts_patched=row.get("Hosts Patched"),
                    missing_patch=row.get("Missing Patch"),
                    latest_version=row.get("Latest Version"),
                    total_hosts=row.get("Total Hosts", 0),
                )
                patch_titles.append(patch)
            except (KeyError, ValueError, TypeError, ValidationError) as e:
                self.log.warning(
                    f"Error processing row at {index}. Skipping this row. Details: {e.__class__.__name__} - {e}."
                )
                skipped_rows += 1

        if skipped_rows > 0:
            self.log.warning(f"{skipped_rows} rows were skipped during PatchTitle creation.")
        self.log.info(f"Successfully created {len(patch_titles)} PatchTitle objects.")

        return patch_titles

    def initialize_dataframe(self, excel_path: Union[Path, str]) -> pd.DataFrame:
        """
        Initializes a DataFrame by reading the Excel file from the provided path.

        :param excel_path: The path to the Excel file, either as a string or a :py:class:`~pathlib.Path` object.
        :type excel_path: :py:obj:`~typing.Union` of :py:obj:`~pathlib.Path` | :py:class:`str`
        :return: A pandas DataFrame loaded from the Excel file.
        :rtype: `pandas.DataFrame`
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
        :type data: :py:obj:`~typing.List` of :py:obj:`~typing.List`
        :param headers: Header names for the columns of the tables.
        :type headers: :py:obj:`~typing.Optional` :py:obj:`~typing.List` of :py:class:`str`
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
        :type threshold: :py:obj:`~typing.Optional` :py:class:`float`
        :param top_n: Number of results to return. If None (default), return all matching results.
        :type top_n: :py:obj:`~typing.Optional` :py:class:`int`
        :return: Filtered and sorted list of ``PatchTitle`` objects.
        :rtype: :py:obj:`~typing.List` of :class:`~patcher.models.patch.PatchTitle`
        """
        self.log.debug(f"Attempting to filter titles by {criteria}.")

        sort_criteria: Dict[FilterCriteria, Callable[[], List[PatchTitle]]] = {
            FilterCriteria.MOST_INSTALLED: lambda: sorted(
                self.patch_titles, key=lambda pt: pt.total_hosts, reverse=True
            ),
            FilterCriteria.LEAST_INSTALLED: lambda: sorted(
                self.patch_titles, key=lambda pt: pt.total_hosts
            ),
            FilterCriteria.OLDEST_LEAST_COMPLETE: lambda: sorted(
                self.patch_titles, key=lambda pt: (pt.released, pt.completion_percent)
            ),
            FilterCriteria.BELOW_THRESHOLD: lambda: sorted(
                [pt for pt in self.patch_titles if pt.completion_percent < threshold],
                key=lambda pt: pt.completion_percent,
            ),
            FilterCriteria.HIGH_MISSING: lambda: sorted(
                [pt for pt in self.patch_titles if pt.missing_patch > (pt.total_hosts * 0.5)],
                key=lambda pt: pt.missing_patch,
            ),
            FilterCriteria.RECENT_RELEASE: lambda: sorted(
                [
                    pt
                    for pt in self.patch_titles
                    if pd.Timestamp(pt.released) >= pd.Timestamp.now() - pd.DateOffset(weeks=1)
                ],
                key=lambda pt: pt.released,
                reverse=True,
            ),
            FilterCriteria.ZERO_COMPLETION: lambda: [
                pt for pt in self.patch_titles if pt.completion_percent == 0
            ],
            FilterCriteria.TOP_PERFORMERS: lambda: sorted(
                [pt for pt in self.patch_titles if pt.completion_percent > 90],
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
