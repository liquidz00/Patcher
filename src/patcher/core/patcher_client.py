"""
Top-level class for Patcher's library use: composes the per-service clients and
data layer into a single object library callers instantiate.

For raw, lower-level access without ``PatcherClient``, see
:class:`patcher.clients.jamf.JamfClient` (Jamf API directly),
:class:`patcher.clients.patcher_api.PatcherAPIClient` (Patcher catalog),
and :class:`patcher.clients.HTTPClient` (generic httpx with truststore).
"""

import asyncio
import warnings
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from ..clients.installomator import InstallomatorClient
from ..clients.jamf import JamfClient
from ..clients.patcher_api import DriftEntry, DriftResponse, PatcherAPIClient
from .analyze import (
    Diff,
    DiffResult,
    TitleFilter,
    TrendAnalysis,
    append_ios_status,
    omit_recent,
    sort_titles,
)
from .config_manager import ConfigManager
from .data_manager import DataManager
from .exceptions import PatcherError
from .exporter import Exporter
from .logger import LogMe
from .matching import match_titles
from .models.patch import PatchTitle
from .models.settings import PatcherSettings, UIConfigKeys, UIDefaults
from .serialization import excel_to_titles


class PatcherClient:
    """
    Patcher's top-level library entry point.

    Composes the Jamf client, the catalog API client, and the data layer into
    one object library callers instantiate directly (or build from on-disk
    state via :meth:`from_state`). The CLI constructs the same object after its
    ``Setup`` flow. Construction parameters are documented on :meth:`__init__`.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        server: str | None = None,
        *,
        config: ConfigManager | None = None,
        concurrency: int = 5,
        disable_cache: bool = False,
        debug: bool = False,
        enable_matching: bool = True,
        enable_homebrew: bool = False,
        ui_config: dict | None = None,
        ignored_titles: list[str] | None = None,
        enable_installomator: bool | None = None,  # deprecated alias for enable_matching
    ):
        """
        Construct a ``PatcherClient`` with all collaborators wired up.

        Library callers pass credentials directly::

            from patcher import PatcherClient

            async with PatcherClient(
                client_id="...",
                client_secret="...",
                server="https://myorg.jamfcloud.com",
            ) as patcher:
                summaries = await patcher.jamf.get_summaries(
                    await patcher.jamf.get_policies()
                )
            # connection pool released here

        An in-memory :class:`~patcher.core.config_manager.ConfigManager` is built internally. No keyring
        backend required, no plist mutation, no disk I/O on construction.
        ``PatcherClient`` is usable as an async context manager (preferred
        for clean shutdown) or as a regular object (call :meth:`aclose`
        manually when done).

        Exactly one of ``(client_id + client_secret + server)`` or
        ``config`` must be provided.

        .. note::

           The ``config=`` parameter exists for internal CLI use, where the
           ``Setup`` flow has already populated keyring with credentials.
           Library callers should use the credentials path above.

        :param client_id: Jamf Pro API client ID.
        :type client_id: str | None
        :param client_secret: Jamf Pro API client secret.
        :type client_secret: str | None
        :param server: Jamf Pro instance URL (e.g. ``https://myorg.jamfcloud.com``).
        :type server: str | None
        :param config: Existing ``ConfigManager`` instance, mutually
            exclusive with the credentials arguments.
        :type config: :class:`~patcher.core.config_manager.ConfigManager` | None
        :param concurrency: Maximum concurrent API requests. Defaults to 5,
            the recommended ceiling per the `Jamf Developer Guide
            <https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices>`_.
        :type concurrency: int
        :param disable_cache: If True, :class:`DataManager` skips on-disk
            patch-data caching.
        :type disable_cache: bool
        :param debug: Enables debug-mode handling in collaborators (notably
            disables the spinner animation when set in the CLI path).
        :type debug: bool
        :param enable_matching: If False, :attr:`api` is ``None`` and all
            catalog matching (Installomator labels and Homebrew Cask) is
            skipped. Defaults to True.
        :type enable_matching: bool
        :param enable_homebrew: Default for whether :meth:`fetch_patches`
            widens matching to the Homebrew Cask source so cask-only titles
            can match, recording matched cask slugs under
            :attr:`~patcher.core.models.patch.PatchTitle.sources`. Has
            no effect when :attr:`api` is ``None`` (i.e.
            ``enable_matching=False``), since matching rides on the same
            catalog client. Defaults to False.
        :type enable_homebrew: bool
        :param ui_config: Optional dict of UI settings (header text,
            footer, font paths, header color, etc.) for PDF/HTML report
            styling. Defaults to :class:`UIDefaults` values.
        :type ui_config: dict | None
        :param ignored_titles: Extra Jamf-title skip patterns merged with the
            built-in :data:`~patcher.policy.IGNORED_TITLES` during matching.
            Defaults to none.
        :type ignored_titles: list[str] | None
        :param enable_installomator: Deprecated alias for ``enable_matching``,
            kept for backward compatibility. Emits a ``DeprecationWarning``
            when passed; remove in favor of ``enable_matching``.
        :type enable_installomator: bool | None
        :raises PatcherError: If neither credentials nor ``config`` are
            provided.
        """
        self.log = LogMe(self.__class__.__name__)

        if config is None:
            if not (client_id and client_secret and server):
                raise PatcherError(
                    "PatcherClient requires either `config=` or all three of "
                    "`client_id`, `client_secret`, and `server`.",
                )
            config = ConfigManager(
                in_memory_credentials={
                    "CLIENT_ID": client_id,
                    "CLIENT_SECRET": client_secret,
                    "URL": server,
                }
            )

        if enable_installomator is not None:
            warnings.warn(
                "`enable_installomator` is deprecated; use `enable_matching` instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            enable_matching = enable_installomator

        self._config = config
        self.debug = debug
        self.jamf = JamfClient(config=config, concurrency=concurrency)
        self.api = PatcherAPIClient(max_concurrency=concurrency) if enable_matching else None
        self.enable_homebrew = enable_homebrew
        self.ignored_titles = ignored_titles or []
        # Resolve ui_config before DataManager so PDF export gets the user's branding, not UIDefaults. See #69.
        self.ui_config = ui_config if ui_config is not None else UIDefaults().model_dump()
        self.data = DataManager(disable_cache=disable_cache)

    @classmethod
    def from_state(cls, **overrides: Any) -> "PatcherClient":
        """
        Construct a ``PatcherClient`` using state already persisted on this Mac.

        Reads Jamf credentials from the macOS keychain, UI customization
        from the property list, and the ``enable_matching`` /
        ``enable_homebrew`` toggles.
        Equivalent to what the ``patcherctl`` CLI does on startup; useful
        for library callers running on a workstation that has already been
        through the setup wizard.

        Any keyword argument accepted by ``__init__`` can be passed as
        an override (commonly ``concurrency`` or ``debug``).

        :param overrides: Optional ``PatcherClient`` constructor kwargs that
            take precedence over what's read from on-disk state.
        :return: A configured ``PatcherClient`` ready to call.
        :rtype: :class:`PatcherClient`
        :raises PatcherError: If keychain credentials are missing (i.e.
            ``patcherctl`` setup hasn't completed on this machine).
        """
        settings = PatcherSettings.load()

        kwargs: dict[str, Any] = {
            "config": ConfigManager(),
            "enable_matching": settings.enable_matching,
            "enable_homebrew": settings.integrations.homebrew,
            "ui_config": settings.user_interface_settings.model_dump(),
            "ignored_titles": settings.ignored_titles,
        }
        kwargs.update(overrides)

        return cls(**kwargs)

    async def fetch_patches(
        self,
        *,
        match_installomator: bool = True,
        match_homebrew: bool | None = None,
        include_ios: bool = False,
        sort_by: str | None = None,
        omit_recent_hours: int | None = None,
    ) -> list[PatchTitle]:
        """
        Fetch patch summaries in one call. The library equivalent of what the
        CLI's ``export`` flow gathers before writing a report.

        Composes the granular pipeline: policies → summaries → (optional
        Installomator match) → (optional iOS append) → (optional sort/filter).
        Equivalent to manually chaining ``self.jamf.get_policies``,
        ``self.jamf.get_summaries``,
        :func:`~patcher.core.matching.match_titles`,
        :func:`~patcher.core.analyze.append_ios_status`,
        :func:`~patcher.core.analyze.omit_recent`, and
        :func:`~patcher.core.analyze.sort_titles`.

        :param match_installomator: If True (default), match each title to
            its Installomator label via the Patcher API catalog
            (:func:`~patcher.core.matching.match_titles`). No-op when
            ``enable_matching=False`` was passed at construction time.
        :type match_installomator: bool
        :param match_homebrew: Whether to widen matching to the Homebrew Cask
            source so cask-only titles can match, recording matched cask slugs
            under :attr:`~patcher.core.models.patch.PatchTitle.sources`.
            ``None`` (default) falls back to the ``enable_homebrew`` value
            set at construction time. Rides on the same match pass as
            Installomator, so it is a no-op when ``match_installomator`` is
            False or :attr:`api` is ``None``.
        :type match_homebrew: bool | None
        :param include_ios: If True, append per-iOS-version summaries to the
            returned list. Costs additional Jamf API calls.
        :type include_ios: bool
        :param sort_by: Optional attribute name to sort titles by (e.g.
            ``"released"``, ``"completion_percent"``). Normalized to
            lowercase + underscores.
        :type sort_by: str | None
        :param omit_recent_hours: If provided, drop titles released within
            the past ``N`` hours. Mirrors the CLI's ``--omit`` flag.
        :type omit_recent_hours: int | None
        :return: List of ``PatchTitle`` objects, optionally enriched and filtered.
        :rtype: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :raises PatcherError: If the Jamf API calls fail or sort_by names
            an attribute that doesn't exist on ``PatchTitle``.
        """
        configs = await self.jamf.get_title_configs()
        titles = await self.jamf.get_summaries([config.get("id") for config in configs])

        name_id_by_title = {
            config.get("softwareTitleId"): config.get("softwareTitleNameId") for config in configs
        }
        for title in titles:
            title.name_id = name_id_by_title.get(title.title_id)

        if match_installomator and self.api is not None:
            include_homebrew = self.enable_homebrew if match_homebrew is None else match_homebrew
            await match_titles(
                titles,
                jamf=self.jamf,
                api=self.api,
                include_homebrew=include_homebrew,
                ignored_titles=self.ignored_titles,
            )

        if include_ios:
            titles = await append_ios_status(titles, self.jamf)

        if omit_recent_hours is not None:
            titles = await omit_recent(titles, hours=omit_recent_hours)

        if sort_by:
            titles = await sort_titles(titles, sort_by)

        return titles

    async def analyze(
        self,
        titles: list[PatchTitle],
        criteria: str,
        *,
        threshold: float | None = 70.0,
        top_n: int | None = None,
        where: dict | None = None,
    ) -> list[PatchTitle]:
        """
        Filter and sort patch titles by a named criterion. The library
        equivalent of the CLI's ``analyze`` subcommand.

        Accepts a CLI-style criterion string (e.g. ``"most-installed"``,
        ``"below-threshold"``). Library callers who want type-checked,
        autocomplete-friendly access should construct
        :class:`~patcher.core.analyze.TitleFilter` directly and invoke the
        matching method.

        .. versionchanged:: 3.0
           The ``criteria`` parameter no longer accepts ``FilterCriteria``
           enum values; the enum was removed in favor of
           :class:`~patcher.core.analyze.TitleFilter` methods. Pass the
           kebab-case string form, or use ``TitleFilter`` directly.

        :param titles: Patch titles to analyze. Typically the output of
            :meth:`fetch_patches`.
        :type titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :param criteria: CLI-style criterion (e.g. ``"most-installed"``).
            See :class:`~patcher.core.analyze.TitleFilter` for the full list.
        :type criteria: str
        :param threshold: Completion-percent threshold for ``below-threshold``
            criterion. Ignored by other criteria. Defaults to 70.0.
        :type threshold: float | None
        :param top_n: If provided, return at most ``top_n`` results. The
            ``below-threshold`` and ``zero-completion`` criteria ignore this
            (they return all matching titles).
        :type top_n: int | None
        :param where: Optional pre-filter applied before the criterion runs.
            Keys are ``min_compliance`` / ``min_hosts`` / ``released_after``;
            unknown keys raise ``PatcherError``.
        :type where: dict | None
        :return: Filtered + sorted list of ``PatchTitle`` objects.
        :rtype: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :raises PatcherError: If ``criteria`` is not a recognized value.
        """
        return TitleFilter.apply(titles, criteria, threshold=threshold, top_n=top_n, where=where)

    async def analyze_excel(
        self,
        excel_path: str | Path,
        criteria: str,
        *,
        threshold: float | None = 70.0,
        top_n: int | None = None,
        where: dict | None = None,
    ) -> list[PatchTitle]:
        """
        Filter and sort patch titles loaded from a saved Excel report.

        Hydrates ``PatchTitle`` objects from ``excel_path`` (a previously-exported
        Patcher report) and analyzes those instead of the cached snapshot — the
        library equivalent of ``patcherctl analyze --excel-file``. Useful for
        re-analyzing a shared or historical export without re-fetching from Jamf.

        :param excel_path: Path to a previously-exported Patcher Excel report.
        :type excel_path: str | :class:`pathlib.Path`
        :param criteria: CLI-style filter criterion.
        :type criteria: str
        :param threshold: Completion-percent cutoff for ``below-threshold``.
        :type threshold: float | None
        :param top_n: Optional result cap. Ignored by ``below-threshold`` and
            ``zero-completion``.
        :type top_n: int | None
        :param where: Optional pre-filter (``min_compliance`` / ``min_hosts`` /
            ``released_after``), same as :meth:`analyze`.
        :type where: dict | None
        :return: Filtered + sorted titles.
        :rtype: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :raises PatcherError: If the Excel file can't be read or yields no titles.
        """
        titles = excel_to_titles(excel_path)
        return await self.analyze(titles, criteria, threshold=threshold, top_n=top_n, where=where)

    async def analyze_trend(
        self,
        criteria: str,
        *,
        save_to: str | Path | None = None,
    ):
        """
        Compute trend analysis across every cached patch dataset.

        Library equivalent of ``patcherctl analyze --all-time --criteria``.
        Reads every cached snapshot in the data cache and builds a trend
        DataFrame keyed on the requested criterion.

        .. versionchanged:: 3.0
           The ``criteria`` parameter no longer accepts ``TrendCriteria``
           enum values; the enum was removed in favor of
           :class:`~patcher.core.analyze.TrendAnalysis` methods. Pass the
           kebab-case string form, or use ``TrendAnalysis`` directly.

        :param criteria: CLI-style trend criterion (e.g.
            ``"patch-adoption"``, ``"release-frequency"``,
            ``"completion-trends"``).
        :type criteria: str
        :param save_to: Optional path. When provided, the trend DataFrame is
            also written to disk as HTML. Parent directories are created if
            needed.
        :type save_to: str | ~pathlib.Path | None
        :return: Trend results as a ~pandas.DataFrame.
        :rtype: ~pandas.DataFrame
        :raises PatcherError: If fewer than two cached snapshots exist or
            ``criteria`` is unrecognized.
        """
        trend_df = TrendAnalysis.apply(self.data.get_cached_files(), criteria)

        if save_to is not None and not trend_df.empty:
            save_to_path = Path(save_to)
            save_to_path.parent.mkdir(parents=True, exist_ok=True)
            trend_df.to_html(save_to_path, index=False)

        return trend_df

    async def diff(
        self,
        *,
        since: timedelta | None = None,
        all_time: bool = False,
        between: tuple[date, date] | None = None,
        no_fetch: bool = False,
    ) -> DiffResult:
        """
        Pairwise comparison between two patch-state snapshots.

        Default (no flags): live fetch via :meth:`fetch_patches` compared
        against the most-recent cached snapshot. Override behavior with one
        of the keyword arguments below.

        .. versionadded:: 3.1

        :param since: When set, compare against the earliest cached snapshot
            in the trailing window (e.g. ``timedelta(days=30)`` for "what
            changed in the last 30 days").
        :type since: ~datetime.timedelta | None
        :param all_time: When True, compare against the earliest cached
            snapshot ever recorded. Mutually exclusive with ``since``.
        :type all_time: bool
        :param between: Two-date pair selecting cached snapshots closest to
            each date. Implies cache-only (no live fetch). Cannot be combined
            with ``since`` or ``all_time``.
        :type between: tuple[~datetime.date, ~datetime.date] | None
        :param no_fetch: When True, skip the live fetch and compare two
            cached snapshots only. Defaults to the second-most-recent and
            most-recent unless ``since`` or ``all_time`` is also passed.
        :type no_fetch: bool
        :return: Structured delta covering added, removed, and changed titles.
        :rtype: :class:`~patcher.core.analyze.DiffResult`
        :raises PatcherError: On invalid flag combinations, or when no
            cached snapshots are available for the requested mode.
        """
        if since is not None and all_time:
            raise PatcherError(
                "`since` and `all_time` are mutually exclusive.",
            )
        if between is not None and (since is not None or all_time):
            raise PatcherError(
                "`between` cannot be combined with `since` or `all_time`.",
            )
        if between is not None and no_fetch:
            raise PatcherError(
                "`no_fetch` is redundant with `between`.",
            )

        if between is not None:
            return Diff.from_cache(self.data, between=between).compute()

        if no_fetch:
            return Diff.from_cache(self.data, since=since, all_time=all_time).compute()

        titles = await self.fetch_patches()
        return Diff.live_vs_cache(titles, self.data, since=since, all_time=all_time).compute()

    async def detect_drift(
        self,
        *,
        slug: str | None = None,
        vendor: str | None = None,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> DriftResponse | DriftEntry | None:
        """
        Cross-source version drift detection via the Patcher catalog API.

        Without ``slug``: returns a :class:`~patcher.clients.patcher_api.DriftResponse`
        listing apps whose upstream sources disagree on the current
        version. With ``slug``: returns a :class:`~patcher.clients.patcher_api.DriftEntry`
        for that single app, or ``None`` if the app doesn't exist or has
        no drift.

        Works without ``enable_matching``; the catalog API is
        constructed on demand when needed.

        .. versionadded:: 3.1

        :param slug: When set, narrow to a single app. Filters below are
            ignored. ``None`` returns the paginated list.
        :type slug: str | None
        :param vendor: Case-insensitive exact vendor match for list mode.
        :type vendor: str | None
        :param source: Drop list entries where this source did not
            participate in the disagreement.
        :type source: str | None
        :param limit: Max entries per list page.
        :type limit: int
        :param offset: Entries to skip before the list page.
        :type offset: int
        :return: Drift result. Shape depends on whether ``slug`` was set.
        :rtype: :class:`~patcher.clients.patcher_api.DriftResponse` | :class:`~patcher.clients.patcher_api.DriftEntry` | None
        :raises PatcherError: If list-mode filters are passed with a slug.
        """
        if slug is not None and (vendor is not None or source is not None):
            raise PatcherError(
                "List-mode filters (`vendor`, `source`) cannot be combined with `slug`.",
            )

        api = self.api
        own_api = False
        if api is None:
            api = PatcherAPIClient()
            own_api = True
        try:
            if slug is not None:
                return await api.get_app_drift(slug)
            return await api.list_drift(vendor=vendor, source=source, limit=limit, offset=offset)
        finally:
            if own_api:
                await api.aclose()

    async def export(
        self,
        titles: list[PatchTitle],
        *,
        output_dir: str | Path,
        formats: set[str] | None = None,
        report_title: str | None = None,
        date_format: str = "%B %d %Y",
        header_color: str | None = None,
        analysis: bool = False,
        device_reports: dict[str, list] | None = None,
    ) -> dict[str, str]:
        """
        Export patch titles to one or more report formats. Builds and caches
        the canonical snapshot via :class:`DataManager`, then renders it through
        :class:`~patcher.core.exporter.Exporter`.

        :param titles: Patch titles to include in the report.
        :type titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :param output_dir: Directory to write report file(s) into.
        :type output_dir: str | Path
        :param formats: Set of format strings to emit. Defaults to all four:
            ``{"excel", "html", "pdf", "json"}``.
        :type formats: set[str] | None
        :param report_title: Title used in PDF/HTML headers. Defaults to the
            ``header_text`` value from this client's ``ui_config``.
        :type report_title: str | None
        :param date_format: Date format for PDF/HTML headers (strftime).
            Defaults to ``"%B %d %Y"``.
        :type date_format: str
        :param header_color: Hex color for the HTML report header background.
            Falls back to :attr:`~patcher.core.models.settings.UIDefaults.header_color` when ``None``.
        :type header_color: str | None
        :param analysis: If True, treats this as an analysis report (affects
            HTML output path naming).
        :type analysis: bool
        :param device_reports: Optional per-title device detail data for
            Excel's per-title sheets.
        :type device_reports: dict[str, list] | None
        :return: Mapping of format → output path for every report written.
        :rtype: dict[str, str]
        """
        df = await asyncio.to_thread(self.data.build_and_cache, titles)
        exporter = Exporter(titles, ui_config=self.ui_config)
        exported = await exporter.export(
            df,
            output_dir=output_dir,
            report_title=report_title
            or self.ui_config.get(UIConfigKeys.HEADER.value, "Patch Report"),
            analysis=analysis,
            date_format=date_format,
            formats=formats,
            header_color=header_color,
            device_reports=device_reports,
        )
        # Track the latest Excel so get_latest_dataset can prefer it as a dataset source.
        if "excel" in exported:
            self.data.latest_excel_file = Path(exported["excel"])
        return exported

    async def reset(
        self,
        kind: Literal["full", "UI", "creds", "cache"],
        *,
        credential: Literal["url", "client_id", "client_secret"] | None = None,
    ) -> None:
        """
        Reset persisted state on this Mac. Library equivalent of
        ``patcherctl reset <kind>``.

        Unlike the CLI, :meth:`reset` does **not** re-launch the setup
        wizard after a full reset — library callers can re-construct a
        ``PatcherClient`` themselves once they've supplied new credentials.

        Kinds:

        - ``"cache"`` — empty the on-disk patch-data cache. Works in any mode.
        - ``"creds"`` — delete Jamf credentials from the keychain. Pass
          ``credential=`` to scope to a single key. Requires keychain-backed
          mode (raises in in-memory mode).
        - ``"UI"`` — clear UI customization from the property list. Requires
          keychain-backed mode.
        - ``"full"`` — every reset above, plus clears the ``setup_completed``
          flag so the next ``patcherctl`` invocation re-runs the wizard.

        :param kind: One of ``"full"``, ``"UI"``, ``"creds"``, ``"cache"``.
        :type kind: str
        :param credential: When ``kind="creds"``, restrict deletion to this
            single credential. One of ``"url"``, ``"client_id"``,
            ``"client_secret"``.
        :type credential: str | None
        :raises PatcherError: If ``kind`` is not ``"cache"`` and this client
            was constructed with in-memory credentials (nothing on disk to
            reset).
        """
        if kind == "cache":
            if not self.data.reset_cache():
                raise PatcherError("Reset cache: failure removing cached data.")
            InstallomatorClient.purge_legacy_disk_cache()
            return

        if self._config.in_memory_mode:
            raise PatcherError(
                f"reset(kind={kind!r}) requires keychain-backed credentials; "
                "this client was constructed with in-memory credentials.",
            )

        if kind == "creds":
            if credential is None:
                self._config.reset_config()
            else:
                # Map the CLI-style argument to the keyring service-account name.
                key_map = {
                    "url": "URL",
                    "client_id": "CLIENT_ID",
                    "client_secret": "CLIENT_SECRET",
                }
                self._config.set_credential(key_map[credential], "")
            return

        if kind == "UI":
            settings = PatcherSettings.load()
            settings.user_interface_settings = UIDefaults()
            settings.save()
            return

        if kind == "full":
            self._config.reset_config()
            settings = PatcherSettings.load()
            settings.user_interface_settings = UIDefaults()
            settings.setup_completed = False
            settings.save()
            self.data.reset_cache()
            return

        raise PatcherError(
            f"reset(kind={kind!r}) is not a recognized reset kind.",
            allowed=("full", "UI", "creds", "cache"),
        )

    async def aclose(self) -> None:
        """
        Release the underlying httpx connection pools.

        Idempotent. Safe to call multiple times. Closes both the JamfClient
        and (when present) the PatcherAPIClient.
        """
        await self.jamf.aclose()
        if self.api is not None:
            await self.api.aclose()

    async def __aenter__(self) -> "PatcherClient":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.aclose()
