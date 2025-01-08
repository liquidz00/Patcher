import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Union

import pandas as pd
from pydantic import ValidationError

from ..models.patch import PatchTitle
from .exceptions import FetchError, PatcherError
from .logger import LogMe


class DataManager:

    _IGNORED = ["install_label"]

    def __init__(self, disable_cache: bool = False):
        """
        The ``DataManager`` class handles data management for patch reports, including caching, validation and exporting to Excel.

        Data caching can be disabled by setting ``disable_cache`` to ``True`` at runtime.

        :param disable_cache: Whether caching functionality should be disabled.
        :type disable_cache: :py:class:`bool`
        """
        self.cache_dir = Path.home() / "Library/Caches/Patcher"
        self.cache_expiration_days = 30
        self.latest_excel_file: Optional[Path] = None
        self.log = LogMe(self.__class__.__name__)
        self._disabled = disable_cache
        self._titles: Optional[List[PatchTitle]] = None

    @property
    def cache_off(self) -> bool:
        """
        Indicates whether caching is disabled.

        :return: True if caching is disabled, False otherwise.
        :rtype: :py:class:`bool`
        """
        return self._disabled

    @property
    def titles(self) -> List[PatchTitle]:
        """
        Retrieve and validate the current list of ``PatchTitle`` objects.

        If titles are not already loaded, they are fetched from the latest available dataset.

        :return: The validated list of ``PatchTitle`` objects.
        :rtype: :py:obj:`~typing.List` [:class:`~patcher.models.patch.PatchTitle`]
        :raises PatcherError: If validation fails.
        """
        if self._titles is None:
            self.log.debug("Attempting to load PatchTitle objects from the latest dataset.")
            df = self._validate_data()
            self._titles = self._create_patches(df)
        return self._titles

    @titles.setter
    def titles(self, value: List[PatchTitle]) -> None:
        """
        Validates and sets the PatchTitle objects. Ensures the list is non-empty.

        :param value: The list of PatchTitle objects to validate.
        :type value: :py:obj:`~typing.Iterable` [:class:`~patcher.models.patch.PatchTitle`]
        :raises PatcherError: If value is not an iterable object.
        :raises FetchError: If any object in the passed iterable object is not a ``PatchTitle`` object, or if titles could not be validated.
        """
        if not isinstance(value, list):
            raise PatcherError(f"Value {value} must be an list of PatchTitle objects.")

        validated_titles = []
        for item in value:
            if not isinstance(item, PatchTitle):
                raise PatcherError(f"Item {item} in list is not of PatchTitle type.")
            validated_titles.append(item)

        if not validated_titles:  # Ensure the list is not empty
            raise FetchError("PatchTitles cannot be set to an empty list.")

        self._titles = validated_titles

    def _validate_data(self) -> pd.DataFrame:
        dataset = self.get_latest_dataset()
        if not dataset:
            raise PatcherError("No dataset available, unable to proceed with validation.")
        try:
            if dataset.suffix == ".pkl":
                with open(dataset, "rb") as f:
                    return pickle.load(f)
            elif dataset.suffix in [".xlsx", ".xls"]:
                return pd.read_excel(dataset)
            else:
                raise PatcherError("Unsupported data format for dataset.", received=dataset.suffix)
        except (FileNotFoundError, pd.errors.EmptyDataError, pickle.UnpicklingError) as e:
            raise PatcherError("Error encountered validating dataset.", error_msg=str(e))

    def _cache_data(self, df: pd.DataFrame):
        """Cache exported data for later use."""
        if self.cache_off:
            return  # Only cache if enabled

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        cache_file = self.cache_dir / f"patch_data_{timestamp}.pkl"
        self.log.debug(f"Attempting to cache data to {cache_file}.")
        try:
            with open(cache_file, "wb") as file:
                pickle.dump(df, file)  # type: ignore
            self.log.info(f"Cached data successfully to {cache_file}")
            self._clean_cache()
        except (FileNotFoundError, pickle.PicklingError, PermissionError, OSError) as e:
            exception_name = type(e).__name__
            self.log.warning(
                f"Unable to cache data to {cache_file} as expected due to {exception_name}. Details: {e}"
            )
            return

    def _clean_cache(self):
        """Remove cache files older than expiration policy."""
        expiration_time = datetime.now() - timedelta(days=self.cache_expiration_days)
        self.log.debug(f"Attempting to remove cache files older than {expiration_time}.")
        for file in self.cache_dir.iterdir():
            if file.is_file() and file.suffix == ".pkl":
                file_time = datetime.fromtimestamp(file.stat().st_mtime)
                if file_time < expiration_time:
                    try:
                        file.unlink()
                        self.log.info(f"Deleted expired cache file: {file}")
                    except OSError as e:
                        self.log.warning(f"Failed to delete cache file {file}. Details: {e}")
                        return

    def _create_dataframe(self, patch_titles: List[PatchTitle]) -> pd.DataFrame:
        """Converts list of PatchTitles into a pandas DataFrame."""
        self.log.debug("Attempting to create DataFrame from PatchTitle objects.")
        try:
            df = pd.DataFrame([patch.model_dump() for patch in patch_titles])
            df.columns = [column.replace("_", " ").title() for column in df.columns]
            df = df.drop(columns=DataManager._IGNORED, errors="ignore")  # Drop excluded columns
            self.log.info(
                f"Created DataFrame from {len(patch_titles)} PatchTitle objects successfully."
            )
            return df
        except (ValueError, pd.errors.EmptyDataError) as e:
            raise PatcherError("Encountered error creating DataFrame.", error_msg=str(e))

    def _create_patches(self, df: pd.DataFrame) -> List[PatchTitle]:
        """Convert a pandas DataFrame into a list of PatchTitle objects."""
        self.log.debug(f"Creating PatchTitle objects from DataFrame with {len(df)} rows.")
        skipped_rows = 0
        patch_titles = []

        for index, row in df.iterrows():
            try:
                patch = PatchTitle(
                    **{key.lower().replace(" ", "_"): value for key, value in row.items()}
                )
                patch_titles.append(patch)
            except (KeyError, ValueError, TypeError, ValidationError) as e:
                exception_name = type(e).__name__
                self.log.warning(
                    f"Error processing row at {index} due to {exception_name}. Skipping this row. Details: {e}."
                )
                skipped_rows += 1

        if skipped_rows > 0:
            self.log.warning(f"{skipped_rows} rows were skipped during PatchTitle creation.")
        self.log.info(f"Successfully created {len(patch_titles)} PatchTitle objects.")

        return patch_titles

    def export_to_excel(self, patch_reports: List[PatchTitle], output_dir: Union[str, Path]) -> str:
        """
        This method converts a list of :class:`~patcher.models.patch.PatchTitle` instances into a DataFrame and
        writes it to an Excel file. The file is saved with a timestamp in the filename.

        :param patch_reports: List of ``PatchTitle`` instances containing patch report data.
        :type patch_reports: :py:obj:`~typing.List` [:class:`~patcher.models.patch.PatchTitle`]
        :param output_dir: Directory where the Excel spreadsheet will be saved.
        :type output_dir: :py:obj:`~typing.Union` [:py:class:`str` | :py:class:`~pathlib.Path`]
        :return: Path to the created Excel spreadsheet.
        :rtype: :py:class:`str`
        :raises PatcherError: If the dataframe is unable to be created or the excel file unable to be saved.
        """
        if isinstance(output_dir, Path):
            output_dir = str(output_dir)

        current_date = datetime.now().strftime("%m-%d-%y")
        df = self._create_dataframe(patch_reports)

        self.log.debug("Attempting to export patch reports to Excel.")
        try:
            excel_path = os.path.join(output_dir, f"patch-report-{current_date}.xlsx")
            df.to_excel(excel_path, index=False)
            self.log.info(f"Excel report created successfully to {excel_path}.")
            self._cache_data(df)
            self.latest_excel_file = excel_path
            return excel_path
        except (OSError, PermissionError) as e:
            raise PatcherError(
                "Encountered error saving DataFrame.",
                file_path=str(output_dir),
                error_msg=str(e),
            )

    def reset_cache(self) -> bool:
        """
        Removes all cached files from Cache directory. See :ref:`reset <resetting_patcher>`.

        :return: True if all files were able to be removed, False otherwise.
        :rtype: :py:class:`bool`
        """
        try:
            [file.unlink() for file in self.get_cached_files()]
            return True
        except Exception as e:  # Using intentionally
            exception_name = type(e).__name__
            self.log.warning(f"Encountered {exception_name} during cache reset. Details: {e}")
            return False

    def load_cached_data(self) -> List[pd.DataFrame]:
        """
        Load all cached data files into a list of DataFrames.

        :return: List of pandas DataFrame objects with cached data.
        :rtype: :py:obj:`~typing.List` [pandas.DataFrame]
        """
        dataframes = []
        cached_files = self.get_cached_files()
        for file in cached_files:
            try:
                with open(file, "rb") as f:
                    dataframes.append(pickle.load(f))
                self.log.info(f"Loaded cache data from {file}")
            except (pickle.UnpicklingError, FileNotFoundError) as e:
                self.log.warning(f"Failed to load cached file {file}. Details: {e}")
        return dataframes

    def get_cached_files(self) -> List[Path]:
        """
        Retrieves all cached file Paths.

        :return: A list of ``Path`` objects pointing to cached files.
        :rtype: :py:obj:`~typing.List` [:py:obj:`~pathlib.Path`]
        """
        return [file for file in self.cache_dir.iterdir() if file.suffix == ".pkl"]

    def get_latest_dataset(self) -> Optional[Path]:
        """
        Retrieves the most recent dataset of patch reports and returns the path.

        If a tracked Excel file is available, it is preferred. Otherwise, searches the cache directory.

        :return: Path to the latest dataset (Excel or pickle file), or None if no dataset is found.
        :rtype: :py:obj:`~typing.Optional` [:py:obj:`~pathlib.Path`]
        """
        if self.latest_excel_file and self.latest_excel_file.exists():
            self.log.info(f"Using latest tracked Excel file: {self.latest_excel_file}")
            return self.latest_excel_file

        pickle_files = sorted(
            self.cache_dir.glob("*.pkl"), key=lambda f: f.stat().st_mtime, reverse=True
        )
        if pickle_files:
            self.log.info(f"Using latest cached pickle file: {pickle_files[0]}")
            return pickle_files[0]

        self.log.warning("No datasets found (Excel or pickle).")
        return None
