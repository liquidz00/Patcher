"""On-disk patch-data cache plus DataFrame (de)serialization of patch titles."""

import pickle
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from .exceptions import PatcherError
from .logger import LogMe
from .models.patch import PatchTitle
from .serialization import df_to_titles, titles_to_df


class DataManager:
    """Caches patch data on disk and (de)serializes it between DataFrames and ``PatchTitle`` objects."""

    def __init__(self, disable_cache: bool = False):
        """
        The ``DataManager`` class owns persistence for patch reports: caching
        snapshots on disk and converting between DataFrames and ``PatchTitle``
        objects. Report rendering lives in :class:`~patcher.core.exporter.Exporter`.

        Data caching can be disabled by setting ``disable_cache`` to ``True`` at runtime.

        :param disable_cache: Whether caching functionality should be disabled.
        :type disable_cache: bool
        """
        self.cache_dir = Path.home() / "Library/Caches/Patcher"
        self.cache_expiration_days = 90  # Increase for better trend analysis
        self.latest_excel_file: Path | None = None
        self.log = LogMe(self.__class__.__name__)
        self._disabled = disable_cache
        self._titles: list[PatchTitle] | None = None

    @property
    def cache_off(self) -> bool:
        """
        Indicates whether caching is disabled.

        :return: True if caching is disabled, False otherwise.
        :rtype: bool
        """
        return self._disabled

    @property
    def titles(self) -> list[PatchTitle]:
        """
        Retrieve and validate the current list of ``PatchTitle`` objects.

        If titles are not already loaded, they are fetched from the latest available dataset.

        :return: The validated list of ``PatchTitle`` objects.
        :rtype: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :raises PatcherError: If validation fails.
        """
        if self._titles is None:
            self.log.debug("Attempting to load PatchTitle objects from the latest dataset.")
            df = self._validate_data()
            self._titles = self._create_patches(df)
        return self._titles

    @titles.setter
    def titles(self, value: list[PatchTitle]) -> None:
        """
        Validates and sets the PatchTitle objects. Ensures the list is non-empty.

        :param value: The list of PatchTitle objects to validate.
        :type value: list[PatchTitle]
        :raises PatcherError: If value is not an iterable object.
        :raises PatcherError: If any object in the passed iterable object is not a ``PatchTitle`` object, or if titles could not be validated.
        """
        if not isinstance(value, list):
            raise PatcherError(f"Value {value} must be an list of PatchTitle objects.")

        validated_titles = []
        for item in value:
            if not isinstance(item, PatchTitle):
                raise PatcherError(f"Item {item} in list is not of PatchTitle type.")
            validated_titles.append(item)

        if not validated_titles:  # Ensure the list is not empty
            raise PatcherError("PatchTitles cannot be set to an empty list.")

        self._titles = validated_titles

    def _validate_data(self) -> pd.DataFrame:
        dataset = self.get_latest_dataset()
        if not dataset:
            raise PatcherError("No dataset available, unable to proceed with validation.")
        return self.load(dataset)

    def _create_dataframe(self, patch_titles: list[PatchTitle]) -> pd.DataFrame:
        """Convert a list of ``PatchTitle`` objects into a pandas DataFrame."""
        self.log.debug("Attempting to create DataFrame from PatchTitle objects.")
        try:
            df = titles_to_df(patch_titles)
            df.columns = [column.replace("_", " ").title() for column in df.columns]
            self.log.info(
                f"Created DataFrame from {len(patch_titles)} PatchTitle objects successfully."
            )
            return df
        except (ValueError, pd.errors.EmptyDataError) as e:
            raise PatcherError("Encountered error creating DataFrame.", error_msg=str(e))

    def _cache_data(self, df: pd.DataFrame):
        """Cache exported data for later use."""
        if self.cache_off:
            return  # Only cache if enabled

        timestamp = datetime.now().strftime("%Y%m%d%H%M")
        cache_file = self.cache_dir / f"patch_data_{timestamp}.parquet"
        self.log.debug(f"Attempting to cache data to {cache_file}.")
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache_file)
            self.log.info(f"Cached data successfully to {cache_file}")
            self._clean_cache()
        except (OSError, PermissionError, ValueError) as e:
            exception_name = type(e).__name__
            self.log.warning(
                f"Unable to cache data to {cache_file} as expected due to {exception_name}. Details: {e}"
            )
            return

    def build_and_cache(self, patch_titles: list[PatchTitle]) -> pd.DataFrame:
        """
        Build the canonical DataFrame from ``patch_titles`` and cache it to disk.

        The full-fidelity frame (every column) is what gets cached; callers that
        render reports drop presentation-excluded columns downstream. Caching is
        a no-op when the cache is disabled.

        :param patch_titles: Titles to serialize and snapshot.
        :type patch_titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :return: The canonical DataFrame built from the titles.
        :rtype: pandas.DataFrame
        """
        df = self._create_dataframe(patch_titles)
        self._cache_data(df)
        return df

    def _clean_cache(self):
        """Remove cache files older than expiration policy."""
        expiration_time = datetime.now() - timedelta(days=self.cache_expiration_days)
        self.log.debug(f"Attempting to remove cache files older than {expiration_time}.")
        for file in self.cache_dir.iterdir():
            if file.is_file() and file.suffix in (".parquet", ".pkl"):
                file_time = datetime.fromtimestamp(file.stat().st_mtime)
                if file_time < expiration_time:
                    try:
                        file.unlink()
                        self.log.info(f"Deleted expired cache file: {file}")
                    except OSError as e:
                        self.log.warning(f"Failed to delete cache file {file}. Details: {e}")
                        return

    def _create_patches(self, df: pd.DataFrame) -> list[PatchTitle]:
        """Convert a pandas DataFrame into a list of PatchTitle objects."""
        self.log.debug(f"Creating PatchTitle objects from DataFrame with {len(df)} rows.")
        patch_titles, errors = df_to_titles(df)

        for detail in errors:
            self.log.warning(f"Skipping row during PatchTitle creation. Details: {detail}")
        if errors:
            self.log.warning(f"{len(errors)} rows were skipped during PatchTitle creation.")
        self.log.info(f"Successfully created {len(patch_titles)} PatchTitle objects.")

        return patch_titles

    @staticmethod
    def load(path: Path) -> pd.DataFrame:
        suffix = path.suffix.lower()
        if not path.exists() or not path.is_file():
            raise PatcherError("Dataset path is not a readable file.", path=str(path))

        match suffix:
            case ".parquet":
                return pd.read_parquet(path)
            case ".pkl":
                try:
                    with open(path, "rb") as f:
                        return pickle.load(f)
                except Exception as e:  # Intentional -- multiple errors can be raised here
                    raise PatcherError(
                        "Couldn't read a cached snapshot - it may have been written by a different version of pandas.",
                        path=str(path),
                        error_msg=str(e),
                        recovery="Run `patcherctl reset cache` to clear stale snapshots, then re-export.",
                    )
            case ".xlsx" | ".xls":
                try:
                    return pd.read_excel(path)
                except (pd.errors.EmptyDataError, pd.errors.ParserError) as e:
                    raise PatcherError(
                        "Could not read the Excel dataset.", path=str(path), error_msg=str(e)
                    )
            case _:
                raise PatcherError(
                    "Unsupported dataset file type.",
                    path=str(path),
                    supported=".pkl, .xlsx, .xls, .parquet",
                )

    @staticmethod
    def snapshot_label(path: Path) -> str:
        """Human-readable label for a cached snapshot file (mtime-derived)."""
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return f"snapshot-{mtime.isoformat(timespec='seconds')}"

    @staticmethod
    def closest_snapshot(snapshots: list[Path], target: date) -> Path:
        """Pick the snapshot whose mtime is closest to ``target``."""
        target_dt = datetime.combine(target, datetime.min.time())
        return min(
            snapshots,
            key=lambda p: abs(datetime.fromtimestamp(p.stat().st_mtime) - target_dt),
        )

    def sorted_cached_files(self) -> list[Path]:
        """Return cached snapshot files sorted oldest → newest by mtime."""
        return sorted(self.get_cached_files(), key=lambda p: p.stat().st_mtime)

    @staticmethod
    def select_baseline(
        cached: list[Path],
        *,
        since: timedelta | None = None,
        all_time: bool = False,
        default: Path,
    ) -> Path:
        """
        Pick the baseline (``from``) snapshot from a sorted cache list.

        ``all_time`` selects the earliest snapshot ever cached; ``since`` selects
        the earliest within the trailing window; otherwise ``default`` is used.

        :raises PatcherError: When ``since`` is set but no snapshot falls in the window.
        """
        if all_time:
            return cached[0]
        if since is not None:
            window_start = datetime.now() - since
            in_window = [
                p for p in cached if datetime.fromtimestamp(p.stat().st_mtime) >= window_start
            ]
            if not in_window:
                raise PatcherError(
                    "No cached snapshots in the requested window.",
                    since=str(since),
                )
            return in_window[0]
        return default

    def reset_cache(self) -> bool:
        """
        Removes all cached files from Cache directory. See :ref:`reset <resetting_patcher>`.

        :return: True if all files were able to be removed, False otherwise.
        :rtype: bool
        """
        try:
            for file in self.get_cached_files():
                file.unlink()
            return True
        except OSError as e:
            self.log.warning(f"Encountered {type(e).__name__} during cache reset. Details: {e}")
            return False

    def load_cached_data(self) -> list[pd.DataFrame]:
        """
        Load all cached data files into a list of DataFrames.

        :return: list of pandas DataFrame objects with cached data.
        :rtype: list[~pandas.DataFrame]
        """
        dataframes = []
        for file in self.get_cached_files():
            try:
                dataframes.append(self.load(file))
                self.log.info(f"Loaded cache data from {file}")
            except PatcherError as e:
                self.log.warning(f"Failed to load cached file {file}. Details: {e}")
        return dataframes

    def get_cached_files(self) -> list[Path]:
        """
        Retrieves all cached file Paths.

        :return: A list of ``Path`` objects pointing to cached files.
        :rtype: list[~pathlib.Path]
        """
        return [file for file in self.cache_dir.iterdir() if file.suffix in (".parquet", ".pkl")]

    def get_latest_dataset(self) -> Path | None:
        """
        Retrieves the most recent dataset of patch reports and returns the path.

        If a tracked Excel file is available, it is preferred. Otherwise, searches the cache directory.

        :return: Path to the latest dataset (Excel or pickle file), or None if no dataset is found.
        :rtype: ~pathlib.Path | None
        """
        if self.latest_excel_file and self.latest_excel_file.exists():
            self.log.info(f"Using latest tracked Excel file: {self.latest_excel_file}")
            return self.latest_excel_file

        snapshots = sorted(self.get_cached_files(), key=lambda f: f.stat().st_mtime, reverse=True)
        if snapshots:
            self.log.info(f"Using latest cached snapshot: {snapshots[0]}")
            return snapshots[0]

        self.log.warning("No datasets found (Excel or cached snapshot).")
        return None
