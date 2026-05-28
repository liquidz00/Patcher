import asyncio
import inspect
import pickle
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel

from ..clients.jamf import JamfClient
from .data_manager import DataManager
from .exceptions import APIResponseError, PatcherError
from .logger import LogMe
from .models.patch import PatchTitle

_log = LogMe("analyze")
_CHANGE_FIELDS = ("completion_percent", "hosts_patched", "total_hosts", "latest_version")


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


class TitleChange(BaseModel):
    """A patch title present in both snapshots with at least one field different."""

    title: str
    title_id: str
    from_completion_percent: float
    to_completion_percent: float
    completion_delta: float
    from_hosts_patched: int
    to_hosts_patched: int
    from_total_hosts: int
    to_total_hosts: int
    from_latest_version: str | None = None
    to_latest_version: str | None = None
    version_changed: bool


class DiffResult(BaseModel):
    """
    Pairwise comparison between two patch-state snapshots.

    Captures titles added/removed/changed and aggregate deltas. The
    ``unchanged_count`` is a count rather than a list because unchanged
    titles are typically the majority and the list would balloon the
    result without adding signal. Callers needing the full unchanged set
    still have access to the underlying snapshots.
    """

    from_label: str
    to_label: str
    from_count: int
    to_count: int
    added: list[PatchTitle]
    removed: list[PatchTitle]
    changed: list[TitleChange]
    unchanged_count: int
    avg_completion_delta: float | None = None
    version_bumps: list[TitleChange] = []


class Diff:
    """
    Pairwise comparison between two patch-state snapshots.

    Each side can be a list of :class:`~patcher.core.models.patch.PatchTitle`
    (typical for "live" data from :meth:`fetch_patches`), a pandas DataFrame,
    or a path to a cached pickle / Excel file. The comparison joins by
    ``title_id`` and surfaces titles added, removed, or changed (completion
    percent, hosts patched, total hosts, latest version).

    .. versionadded:: 3.1

    :param from_snapshot: The earlier snapshot (the "before" side).
    :type from_snapshot: ~pandas.DataFrame | list[:class:`PatchTitle`] |
        ~pathlib.Path | str
    :param to_snapshot: The later snapshot (the "after" side).
    :type to_snapshot: ~pandas.DataFrame | list[:class:`PatchTitle`] |
        ~pathlib.Path | str
    :param from_label: Optional human-readable label for the from-side
        (e.g. ``"snapshot-2026-05-20T04:00:00"``). Derived from the input
        type when omitted.
    :type from_label: str | None
    :param to_label: Optional label for the to-side (e.g. ``"live"``).
        Derived from the input type when omitted.
    :type to_label: str | None
    """

    def __init__(
        self,
        from_snapshot: pd.DataFrame | list[PatchTitle] | Path | str,
        to_snapshot: pd.DataFrame | list[PatchTitle] | Path | str,
        *,
        from_label: str | None = None,
        to_label: str | None = None,
    ):
        self._log = LogMe(self.__class__.__name__)
        self._from_input = from_snapshot
        self._to_input = to_snapshot
        self._from_label = from_label or _describe_snapshot(from_snapshot)
        self._to_label = to_label or _describe_snapshot(to_snapshot)

    def compute(self) -> DiffResult:
        """Run the comparison and return a :class:`DiffResult`."""
        from_df = _to_normalized_df(self._from_input)
        to_df = _to_normalized_df(self._to_input)

        if "title_id" not in from_df.columns or "title_id" not in to_df.columns:
            raise PatcherError(
                "Snapshot is missing the `title_id` column required for diff.",
            )

        from_ids = set(from_df["title_id"].astype(str))
        to_ids = set(to_df["title_id"].astype(str))

        added_ids = to_ids - from_ids
        removed_ids = from_ids - to_ids
        common_ids = from_ids & to_ids

        added = _df_rows_to_titles(to_df[to_df["title_id"].astype(str).isin(added_ids)])
        removed = _df_rows_to_titles(from_df[from_df["title_id"].astype(str).isin(removed_ids)])

        # Index both sides by title_id for O(1) lookup during pairwise comparison.
        from_indexed = from_df.set_index(from_df["title_id"].astype(str), drop=False)
        to_indexed = to_df.set_index(to_df["title_id"].astype(str), drop=False)

        changed: list[TitleChange] = []
        unchanged = 0
        for tid in common_ids:
            from_row = from_indexed.loc[tid]
            to_row = to_indexed.loc[tid]
            # Defensive: if duplicates somehow exist, take the first.
            if isinstance(from_row, pd.DataFrame):
                from_row = from_row.iloc[0]
            if isinstance(to_row, pd.DataFrame):
                to_row = to_row.iloc[0]
            if _has_changes(from_row, to_row):
                changed.append(_build_title_change(tid, from_row, to_row))
            else:
                unchanged += 1

        avg = sum(c.completion_delta for c in changed) / len(changed) if changed else None

        return DiffResult(
            from_label=self._from_label,
            to_label=self._to_label,
            from_count=len(from_df),
            to_count=len(to_df),
            added=added,
            removed=removed,
            changed=changed,
            unchanged_count=unchanged,
            avg_completion_delta=avg,
            version_bumps=[c for c in changed if c.version_changed],
        )

    @classmethod
    def from_cache(
        cls,
        data_manager: DataManager,
        *,
        since: timedelta | None = None,
        all_time: bool = False,
        between: tuple[date, date] | None = None,
    ) -> "Diff":
        """
        Construct a :class:`Diff` from the local cache only (no live fetch).

        With no overrides, defaults to the two most recent cached snapshots
        (``from`` is second-most-recent, ``to`` is most-recent).

        :param data_manager: The :class:`DataManager` whose cache to read.
        :param since: When set, ``from`` is the earliest snapshot in the
            trailing window. ``to`` stays the most recent.
        :param all_time: When True, ``from`` is the earliest snapshot ever
            cached. ``to`` stays the most recent.
        :param between: When set, both sides come from cached snapshots
            chosen as the closest mtime to each given date.
        :raises PatcherError: If no cached snapshots exist, or fewer than 2
            snapshots are available for the no-fetch case.
        """
        cached = _sorted_cached_files(data_manager)
        if not cached:
            raise PatcherError(
                "No cached snapshots available; run `patcherctl export` first to seed the cache.",
            )

        if between is not None:
            from_path = _closest_snapshot(cached, between[0])
            to_path = _closest_snapshot(cached, between[1])
            return cls(
                from_path,
                to_path,
                from_label=_snapshot_label(from_path),
                to_label=_snapshot_label(to_path),
            )

        if len(cached) < 2:
            raise PatcherError(
                "Need at least 2 cached snapshots for no-fetch diff.",
                found=len(cached),
            )

        if all_time:
            from_path = cached[0]
        elif since is not None:
            window_start = datetime.now() - since
            in_window = [
                p for p in cached if datetime.fromtimestamp(p.stat().st_mtime) >= window_start
            ]
            if not in_window:
                raise PatcherError(
                    "No cached snapshots in the requested window.",
                    since=str(since),
                )
            from_path = in_window[0]
        else:
            from_path = cached[-2]

        to_path = cached[-1]
        return cls(
            from_path,
            to_path,
            from_label=_snapshot_label(from_path),
            to_label=_snapshot_label(to_path),
        )

    @classmethod
    def live_vs_cache(
        cls,
        live_titles: list[PatchTitle],
        data_manager: DataManager,
        *,
        since: timedelta | None = None,
        all_time: bool = False,
    ) -> "Diff":
        """
        Construct a :class:`Diff` comparing a freshly-fetched live state
        against a cached snapshot.

        With no overrides, ``from`` is the most-recent cached snapshot.

        :param live_titles: PatchTitle objects from a recent ``fetch_patches`` call.
        :param data_manager: The :class:`DataManager` whose cache to read.
        :param since: When set, ``from`` is the earliest snapshot in the trailing window.
        :param all_time: When True, ``from`` is the earliest snapshot ever cached.
        :raises PatcherError: If no cached snapshots are available, or no
            snapshots fall within the requested window.
        """
        cached = _sorted_cached_files(data_manager)
        if not cached:
            raise PatcherError(
                "No cached snapshots available; run `patcherctl export` first to seed the cache.",
            )

        if all_time:
            from_path = cached[0]
        elif since is not None:
            window_start = datetime.now() - since
            in_window = [
                p for p in cached if datetime.fromtimestamp(p.stat().st_mtime) >= window_start
            ]
            if not in_window:
                raise PatcherError(
                    "No cached snapshots in the requested window.",
                    since=str(since),
                )
            from_path = in_window[0]
        else:
            from_path = cached[-1]

        return cls(
            from_path,
            live_titles,
            from_label=_snapshot_label(from_path),
            to_label="live",
        )


def _sorted_cached_files(data_manager: DataManager) -> list[Path]:
    """Return cached snapshot files sorted oldest → newest by mtime."""
    return sorted(data_manager.get_cached_files(), key=lambda p: p.stat().st_mtime)


def _closest_snapshot(snapshots: list[Path], target: date) -> Path:
    """Pick the snapshot whose mtime is closest to ``target``."""
    target_dt = datetime.combine(target, datetime.min.time())
    return min(
        snapshots,
        key=lambda p: abs(datetime.fromtimestamp(p.stat().st_mtime) - target_dt),
    )


def _snapshot_label(path: Path) -> str:
    """Human-readable label for a cached snapshot file (mtime-derived)."""
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return f"snapshot-{mtime.isoformat(timespec='seconds')}"


def _describe_snapshot(snapshot: pd.DataFrame | list[PatchTitle] | Path | str) -> str:
    """Default label for inputs passed directly to ``Diff()``."""
    if isinstance(snapshot, (Path, str)):
        try:
            return _snapshot_label(Path(snapshot))
        except OSError:
            return str(snapshot)
    if isinstance(snapshot, list):
        return "live"
    return "dataframe"


def _to_normalized_df(
    snapshot: pd.DataFrame | list[PatchTitle] | Path | str,
) -> pd.DataFrame:
    """Load any supported snapshot input and normalize column names + dates."""
    if isinstance(snapshot, list):
        df = pd.DataFrame([t.model_dump() for t in snapshot])
    elif isinstance(snapshot, pd.DataFrame):
        df = snapshot.copy()
    elif isinstance(snapshot, (Path, str)):
        df = _read_snapshot_file(Path(snapshot))
    else:
        raise PatcherError(
            "Unsupported snapshot type for Diff.",
            received=type(snapshot).__name__,
        )

    df.columns = [str(col).lower().replace(" ", "_") for col in df.columns]
    if "released" in df.columns:
        df["released"] = pd.to_datetime(df["released"], errors="coerce")
    return df


def _read_snapshot_file(file_path: Path) -> pd.DataFrame:
    """Load a snapshot from a pickle or Excel file."""
    if not file_path.exists() or not file_path.is_file():
        raise PatcherError(
            "Snapshot path is not a readable file.",
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
        "Unsupported snapshot file type.",
        path=str(file_path),
        supported=".pkl, .xlsx, .xls",
    )


def _has_changes(from_row: pd.Series, to_row: pd.Series) -> bool:
    """True if any of the tracked fields differ between the two rows."""
    for field in _CHANGE_FIELDS:
        if field not in from_row.index or field not in to_row.index:
            continue
        f, t = from_row[field], to_row[field]
        if pd.isna(f) and pd.isna(t):
            continue
        if f != t:
            return True
    return False


def _build_title_change(tid: str, from_row: pd.Series, to_row: pd.Series) -> TitleChange:
    return TitleChange(
        title=str(to_row["title"]),
        title_id=tid,
        from_completion_percent=float(from_row["completion_percent"]),
        to_completion_percent=float(to_row["completion_percent"]),
        completion_delta=float(to_row["completion_percent"] - from_row["completion_percent"]),
        from_hosts_patched=int(from_row["hosts_patched"]),
        to_hosts_patched=int(to_row["hosts_patched"]),
        from_total_hosts=int(from_row["total_hosts"]),
        to_total_hosts=int(to_row["total_hosts"]),
        from_latest_version=_optional_str(from_row.get("latest_version")),
        to_latest_version=_optional_str(to_row.get("latest_version")),
        version_changed=_optional_str(from_row.get("latest_version"))
        != _optional_str(to_row.get("latest_version")),
    )


def _df_rows_to_titles(df: pd.DataFrame) -> list[PatchTitle]:
    """Hydrate DataFrame rows back into :class:`PatchTitle` objects."""
    titles: list[PatchTitle] = []
    for _, row in df.iterrows():
        try:
            titles.append(
                PatchTitle(
                    title=str(row.get("title", "")),
                    title_id=str(row.get("title_id", "")),
                    released=_coerce_released(row.get("released")),
                    hosts_patched=int(row.get("hosts_patched", 0) or 0),
                    missing_patch=int(row.get("missing_patch", 0) or 0),
                    latest_version=_optional_str(row.get("latest_version")) or "",
                )
            )
        except Exception as exc:
            _log.warning(f"Failed to hydrate PatchTitle from row: {exc}")
    return titles


def _optional_str(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)


def _coerce_released(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "strftime"):
        return value.strftime("%b %d %Y")
    return str(value)
