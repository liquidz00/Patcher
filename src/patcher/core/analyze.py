import asyncio
import inspect
import pickle
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from ..clients.jamf import JamfClient
from .data_manager import DataManager
from .exceptions import APIResponseError, PatcherError
from .logger import LogMe
from .models.patch import PatchTitle

_log = LogMe("analyze")


async def sort_titles(titles: list[PatchTitle], sort_key: str) -> list[PatchTitle]:
    """
    Sort ``titles`` by the named attribute (case-insensitive, spaces tolerated).

    Offloads the sort to a thread so the event loop stays responsive on
    large lists.

    :param titles: PatchTitle objects to sort.
    :type titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
    :param sort_key: Attribute name to sort by (e.g. ``"released"``,
        ``"completion percent"``). Normalized to lowercase + underscores.
    :type sort_key: str
    :raises PatcherError: If the attribute does not exist on PatchTitle.
    """
    _log.debug(f"Detected sorting option '{sort_key}'")
    key = sort_key.lower().replace(" ", "_")
    try:
        sorted_reports = await asyncio.to_thread(
            lambda: sorted(titles, key=lambda x: getattr(x, key))
        )
        _log.info(f"Patch reports sorted successfully by '{key}'.")
        return sorted_reports
    except (KeyError, AttributeError) as e:
        column = key.title().replace("_", " ")
        _log.error(f"Invalid column name for sorting: {column}. Details: {e}")
        raise PatcherError(
            "Unable to sort patch reports due to invalid column name.",
            column=column,
            error_msg=str(e),
        )


async def omit_recent(titles: list[PatchTitle], hours: int = 48) -> list[PatchTitle]:
    """
    Return ``titles`` with any released within the past ``hours`` hours dropped.

    :param titles: PatchTitle objects to filter.
    :type titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
    :param hours: Lookback window in hours. Defaults to 48.
    :type hours: int
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    _log.debug(f"Omitting reports with patches released since {cutoff}.")
    original_count = len(titles)
    filtered = await asyncio.to_thread(
        lambda: [t for t in titles if datetime.strptime(t.released, "%b %d %Y") < cutoff]
    )
    _log.info(f"Omitted {original_count - len(filtered)} policies with recent patches.")
    return filtered


async def append_ios_status(titles: list[PatchTitle], api: JamfClient) -> list[PatchTitle]:
    """
    Fetch iOS device/version data via ``api`` + the SOFA feed and append
    per-iOS-version :class:`~patcher.core.models.patch.PatchTitle` summaries to ``titles``.

    :param titles: Existing PatchTitle list to extend.
    :type titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
    :param api: Configured ``JamfClient`` used for the device/version
        and SOFA feed calls.
    :type api: :class:`~patcher.clients.jamf.JamfClient`
    :raises PatcherError: If the device list, OS versions, or SOFA feed cannot be fetched.
    """
    _log.debug("Attempting to fetch iOS device IDs.")
    try:
        device_ids = await api.get_device_ids()
        _log.info(f"Received {len(device_ids)} device IDs successfully.")
    except APIResponseError as e:
        _log.error(f"Unable to obtain iOS Device IDs from Jamf instance. Details: {e}")
        raise PatcherError("Unable to obtain iOS Device IDs from Jamf instance.", error_msg=str(e))

    _log.debug("Attempting to fetch iOS version data for enrolled devices.")
    try:
        device_versions = await api.get_device_os_versions(device_ids=device_ids)
        _log.info(f"Successfully obtained OS versions for {len(device_versions)} devices.")
    except APIResponseError as e:
        _log.error(
            f"Received empty response obtaining device OS versions from Jamf instance. Details: {e}"
        )
        raise PatcherError(
            "Failed retrieving iOS Device versions from Jamf instance.",
            ids=device_ids,
            error_msg=str(e),
        )

    _log.debug("Attempting to retrieve SOFA feed.")
    try:
        latest_versions = await api.get_sofa_feed()
        _log.info("Obtained latest version information from SOFA feed successfully.")
    except APIResponseError as e:
        _log.error(f"Failed to fetch data from SOFA feed. Details: {e}")
        raise PatcherError("Error fetching data from SOFA feed.", error_msg=str(e))

    ios_data = calculate_ios_on_latest(
        device_versions=device_versions, latest_versions=latest_versions
    )
    titles.extend(ios_data)
    _log.info("iOS information successfully appended to patch reports.")
    return titles


def calculate_ios_on_latest(
    device_versions: list[dict[str, str]],
    latest_versions: list[dict[str, str]],
) -> list[PatchTitle]:
    """
    Per-major-iOS-version, count devices on the latest release and produce
    :class:`PatchTitle` summaries.

    Pure data transform. No I/O.

    :param device_versions: Per-device dicts containing ``"OS"`` and ``"DeviceID"``.
    :type device_versions: list[dict[str, str]]
    :param latest_versions: SOFA-feed entries containing ``"OSVersion"``,
        ``"ProductVersion"``, ``"ReleaseDate"``.
    :type latest_versions: list[dict[str, str]]
    :raises PatcherError: On unexpected key/zero-division errors during counting.
    """
    _log.debug("Attempting to calculate iOS devices on latest version.")

    try:
        latest_versions_dict = {lv.get("OSVersion"): lv for lv in latest_versions}
        version_counts = {
            version: {"count": 0, "total": 0} for version in latest_versions_dict.keys()
        }
        for device in device_versions:
            device_os = device.get("OS")
            if not device_os:
                _log.warning(f"Device missing OS information: {device}")
            major_version = device_os.split(".")[0]
            if major_version in version_counts:
                version_counts[major_version]["total"] += 1
                if device_os == latest_versions_dict[major_version]["ProductVersion"]:
                    version_counts[major_version]["count"] += 1

        mapped = [
            PatchTitle(
                title=f"iOS {latest_versions_dict[version]['ProductVersion']}",
                title_id="iOS",
                released=latest_versions_dict[version]["ReleaseDate"],
                hosts_patched=counts["count"],
                missing_patch=counts["total"] - counts["count"],
                latest_version=latest_versions_dict[version]["ProductVersion"],
                completion_percent=round((counts["count"] / counts["total"]) * 100, 2),
                total_hosts=counts["total"],
            )
            for version, counts in version_counts.items()
            if counts["total"] > 0
        ]
        _log.info(f"iOS version analysis completed with {len(mapped)} summaries generated.")
        return mapped
    except KeyError as e:
        raise PatcherError(
            "Encountered KeyError while calculating iOS devices on latest version.",
            error_msg=str(e),
        )
    except ZeroDivisionError as e:
        raise PatcherError(
            "Division by zero encountered during iOS Device percentage calculation.",
            error_msg=str(e),
        )


class TitleFilter:
    """
    Apply named filters over a list of :class:`~patcher.core.models.patch.PatchTitle`.

    Each filter is a method on the class. Library callers can chain construction
    and method call: ``TitleFilter(titles).most_installed(top_n=10)``. The CLI
    and :meth:`patcher.core.patcher_client.PatcherClient.analyze` route through
    :meth:`apply`, which maps a CLI-style string (e.g. ``"most-installed"``)
    onto the matching method.

    .. versionchanged:: 3.0
       Replaces the ``FilterCriteria`` enum and the ``Analyzer.filter_titles``
       dispatch table. Each former enum value is now its own method with its
       own signature (e.g. :meth:`below_threshold` accepts ``threshold``;
       :meth:`zero_completion` accepts no extra arguments).

    :param titles: PatchTitle objects to filter.
    :type titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
    """

    def __init__(self, titles: list[PatchTitle]):
        self._titles = list(titles)
        self._log = LogMe(self.__class__.__name__)

    def most_installed(self, top_n: int | None = None) -> list[PatchTitle]:
        """Sort by ``total_hosts`` descending. ``top_n`` caps the result."""
        result = sorted(self._titles, key=lambda pt: pt.total_hosts, reverse=True)
        return self._cap(result, top_n)

    def least_installed(self, top_n: int | None = None) -> list[PatchTitle]:
        """Sort by ``total_hosts`` ascending. ``top_n`` caps the result."""
        result = sorted(self._titles, key=lambda pt: pt.total_hosts)
        return self._cap(result, top_n)

    def oldest_least_complete(self, top_n: int | None = None) -> list[PatchTitle]:
        """Sort by ``released`` then ``completion_percent`` ascending."""
        result = sorted(self._titles, key=lambda pt: (pt.released, pt.completion_percent))
        return self._cap(result, top_n)

    def below_threshold(self, threshold: float = 70.0) -> list[PatchTitle]:
        """
        Titles with ``completion_percent`` strictly below ``threshold``. Sorted
        by completion ascending. All matches are returned (no ``top_n`` cap).
        """
        return sorted(
            [pt for pt in self._titles if pt.completion_percent < threshold],
            key=lambda pt: pt.completion_percent,
        )

    def high_missing(self, top_n: int | None = None) -> list[PatchTitle]:
        """Titles where ``missing_patch`` exceeds 50% of ``total_hosts``."""
        result = sorted(
            [pt for pt in self._titles if pt.missing_patch > (pt.total_hosts * 0.5)],
            key=lambda pt: pt.missing_patch,
        )
        return self._cap(result, top_n)

    def recent_release(self, top_n: int | None = None) -> list[PatchTitle]:
        """Titles released within the last week, sorted newest first."""
        cutoff = pd.Timestamp.now() - pd.DateOffset(weeks=1)
        result = sorted(
            [pt for pt in self._titles if pd.Timestamp(pt.released) >= cutoff],
            key=lambda pt: pt.released,
            reverse=True,
        )
        return self._cap(result, top_n)

    def zero_completion(self) -> list[PatchTitle]:
        """Titles with ``completion_percent`` exactly zero. No ``top_n`` cap."""
        return [pt for pt in self._titles if pt.completion_percent == 0]

    def top_performers(self, top_n: int | None = None) -> list[PatchTitle]:
        """Titles with ``completion_percent`` above 90, sorted descending."""
        result = sorted(
            [pt for pt in self._titles if pt.completion_percent > 90],
            key=lambda pt: pt.completion_percent,
            reverse=True,
        )
        return self._cap(result, top_n)

    def installomator(self, top_n: int | None = None) -> list[PatchTitle]:
        """Titles that carry one or more Installomator labels."""
        result = [pt for pt in self._titles if pt.install_label != []]
        return self._cap(result, top_n)

    @classmethod
    def criteria(cls) -> list[str]:
        """List of CLI-flag-style names for every filter method on this class."""
        return [name.replace("_", "-") for name in _filter_method_names(cls)]

    @classmethod
    def apply(
        cls,
        titles: list[PatchTitle],
        criterion: str,
        *,
        threshold: float | None = None,
        top_n: int | None = None,
    ) -> list[PatchTitle]:
        """
        Resolve a CLI-style criterion string (e.g. ``"most-installed"``,
        ``"below-threshold"``) to the corresponding filter method and invoke
        it with whichever of ``threshold`` / ``top_n`` the method accepts.

        Used by the CLI's ``analyze`` subcommand and by
        :meth:`patcher.core.patcher_client.PatcherClient.analyze`. Library
        callers that already know which filter they want should construct
        directly: ``TitleFilter(titles).most_installed(top_n=10)``.
        """
        method = _resolve_method(cls, titles, criterion)
        kwargs = _accepted_kwargs(method, threshold=threshold, top_n=top_n)
        return method(**kwargs)

    def _cap(self, result: list[PatchTitle], top_n: int | None) -> list[PatchTitle]:
        if top_n is not None and len(result) > top_n:
            return result[:top_n]
        return result


class TrendAnalysis:
    """
    Compose trend analyses across multiple cached patch datasets.

    Combines datasets on construction and exposes one method per trend
    criterion. Library callers can chain: ``TrendAnalysis(datasets).patch_adoption()``.
    The CLI and :meth:`patcher.core.patcher_client.PatcherClient.analyze_trend`
    route through :meth:`apply`, which maps a CLI-style string onto the
    matching method.

    .. versionchanged:: 3.0
       Replaces the ``TrendCriteria`` enum and ``Analyzer.timelapse``. Each
       former enum value is now its own method.

    :param datasets: Pickle / Excel paths or pre-loaded DataFrames. Must
        contain at least two datasets to produce a meaningful trend.
    :type datasets: list[~pandas.DataFrame | ~pathlib.Path | str]
    :raises PatcherError: If fewer than two datasets are provided, or if a
        dataset has an unsupported file type.
    """

    def __init__(self, datasets: list[pd.DataFrame | Path | str]):
        if len(datasets) < 2:
            raise PatcherError(
                "Insufficient data to analyze trends.",
                amount_found=len(datasets),
            )
        self._log = LogMe(self.__class__.__name__)
        self._combined = self._combine_datasets(datasets)

    @classmethod
    def from_cache(cls, data_manager: DataManager) -> "TrendAnalysis":
        """Construct from every cached snapshot the ``DataManager`` has on disk."""
        return cls(data_manager.get_cached_files())

    def patch_adoption(self, sort_by: str | None = None, ascending: bool = True) -> pd.DataFrame:
        """
        Per-title average completion plus the most recent release date.

        :return: DataFrame with columns ``Title``, ``Average Completion``,
            ``Most Recent Release``.
        """
        df = (
            self._combined.groupby("title", as_index=False)
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
                    "Most Recent Release": lambda d: d["Most Recent Release"].dt.strftime(
                        "%Y-%m-%d"
                    ),
                    "Average Completion": lambda d: d["Average Completion"].apply(
                        lambda x: f"{x:.2f}%"
                    ),
                }
            )
        )
        return self._maybe_sort(df, sort_by, ascending)

    def release_frequency(self, sort_by: str | None = None, ascending: bool = True) -> pd.DataFrame:
        """
        Count of distinct release dates per title across the snapshots.

        :return: DataFrame with columns ``Title``, ``Release Count``.
        """
        df = (
            self._combined.groupby("title", as_index=False)
            .agg(release_count=("released", "nunique"))
            .rename(columns={"title": "Title", "release_count": "Release Count"})
        )
        return self._maybe_sort(df, sort_by, ascending)

    def completion_trends(self, sort_by: str | None = None, ascending: bool = True) -> pd.DataFrame:
        """
        Per-release-date average completion across the snapshots.

        :return: DataFrame with columns ``Release Date``, ``Title``,
            ``Average Completion``.
        """
        df = (
            self._combined.groupby(["released", "title"], as_index=False)
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
                    "Release Date": lambda d: d["Release Date"].dt.strftime("%Y-%m-%d"),
                    "Average Completion": lambda d: d["Average Completion"].apply(
                        lambda x: f"{x:.2f}%"
                    ),
                }
            )
        )
        return self._maybe_sort(df, sort_by, ascending)

    @classmethod
    def criteria(cls) -> list[str]:
        """List of CLI-flag-style names for every trend method on this class."""
        return [name.replace("_", "-") for name in _filter_method_names(cls)]

    @classmethod
    def apply(
        cls,
        datasets: list[pd.DataFrame | Path | str],
        criterion: str,
        *,
        sort_by: str | None = None,
        ascending: bool = True,
    ) -> pd.DataFrame:
        """
        Resolve a CLI-style criterion string to the corresponding trend
        method and invoke it.

        Used by the CLI and
        :meth:`patcher.core.patcher_client.PatcherClient.analyze_trend`. Library
        callers that already know which trend they want should construct
        directly: ``TrendAnalysis(datasets).patch_adoption()``.
        """
        instance = cls(datasets)
        method = _resolve_method_on_instance(instance, criterion)
        kwargs = _accepted_kwargs(method, sort_by=sort_by, ascending=ascending)
        return method(**kwargs)

    def _combine_datasets(self, datasets: list[pd.DataFrame | Path | str]) -> pd.DataFrame:
        dataframes = []
        for dataset in datasets:
            if isinstance(dataset, pd.DataFrame):
                df = dataset
            elif isinstance(dataset, (Path, str)):
                self._log.debug(f"Loading dataset from: {dataset}")
                df = self._read_file(Path(dataset))
            else:
                raise PatcherError(
                    "Unsupported dataset type.",
                    received=type(dataset).__name__,
                )

            df.columns = [col.lower().replace(" ", "_") for col in df.columns]
            if "released" in df.columns:
                df["released"] = pd.to_datetime(df["released"], format="%b %d %Y")
            dataframes.append(df)

        combined = pd.concat(dataframes, ignore_index=True)
        self._log.info(f"Combined {len(dataframes)} datasets into a single DataFrame.")
        return combined

    def _read_file(self, file_path: Path) -> pd.DataFrame:
        if not file_path.exists() or not file_path.is_file():
            raise PatcherError(
                "Dataset path is not a readable file.",
                path=str(file_path),
            )

        suffix = file_path.suffix.lower()
        if suffix == ".pkl":
            with open(file_path, "rb") as f:
                return pickle.load(f)
        if suffix in (".xlsx", ".xls"):
            try:
                return pd.read_excel(file_path)
            except pd.errors.EmptyDataError as e:
                raise PatcherError(
                    "The Excel file provided is empty.",
                    path=str(file_path),
                    error_msg=str(e),
                )
            except pd.errors.ParserError as e:
                raise PatcherError(
                    "Unable to parse the Excel file properly.",
                    path=str(file_path),
                    error_msg=str(e),
                )

        raise PatcherError(
            "Unsupported dataset file type.",
            path=str(file_path),
            supported=".pkl, .xlsx, .xls",
        )

    def _maybe_sort(self, df: pd.DataFrame, sort_by: str | None, ascending: bool) -> pd.DataFrame:
        if sort_by is None:
            return df
        if sort_by not in df.columns:
            raise PatcherError(
                "Invalid sorting provided.",
                received=sort_by,
                expected=", ".join(df.columns),
            )
        return df.sort_values(by=sort_by, ascending=ascending)


def _filter_method_names(cls: type) -> list[str]:
    """
    Public method names on ``cls`` that correspond to filter/trend criteria.

    Excludes dunders, private methods, and the class-level helpers
    ``apply`` / ``criteria`` so :meth:`TitleFilter.criteria` and
    :meth:`TrendAnalysis.criteria` reflect only the criterion surface.
    """
    skip = {"apply", "criteria", "from_cache"}
    return [
        name
        for name in vars(cls)
        if not name.startswith("_") and name not in skip and callable(vars(cls)[name])
    ]


def _resolve_method(cls: type, titles: list[PatchTitle], criterion: str):
    instance = cls(titles)
    return _resolve_method_on_instance(instance, criterion)


def _resolve_method_on_instance(instance, criterion: str):
    method_name = criterion.replace("-", "_")
    if method_name.startswith("_") or method_name not in _filter_method_names(type(instance)):
        raise PatcherError(
            "Invalid criteria provided.",
            received=criterion,
            supported=", ".join(type(instance).criteria()),
        )
    return getattr(instance, method_name)


def _accepted_kwargs(method, **kwargs) -> dict:
    """Return only the kwargs ``method`` accepts and that aren't ``None``."""
    sig = inspect.signature(method)
    return {
        name: value
        for name, value in kwargs.items()
        if value is not None and name in sig.parameters
    }
