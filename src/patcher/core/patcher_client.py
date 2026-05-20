"""
Top-level class for Patcher's library use.

Composes the per-service clients (:class:`JamfClient`,
:class:`PatcherAPIClient`) and data layer (:class:`DataManager`) into
a single object library callers instantiate. CLI users construct the
same object via the existing ``Setup`` flow, which populates a
:class:`~patcher.core.config_manager.ConfigManager` and hands it to ``PatcherClient`` through the
``config=`` argument.

For raw, lower-level access without ``PatcherClient``, see
:class:`patcher.clients.jamf.JamfClient` (Jamf API directly),
:class:`patcher.clients.patcher_api.PatcherAPIClient` (Patcher catalog),
and :class:`patcher.clients.HTTPClient` (generic httpx with truststore).
"""

from pathlib import Path
from typing import Any, Literal

from ..clients.jamf import JamfClient
from ..clients.patcher_api import PatcherAPIClient
from .analyze import (
    Analyzer,
    FilterCriteria,
    TrendCriteria,
    append_ios_status,
    omit_recent,
    sort_titles,
)
from .config_manager import ConfigManager
from .data_manager import DataManager
from .exceptions import PatcherError
from .logger import LogMe
from .matching import match_titles
from .models.patch import PatchTitle
from .models.ui import UIConfigKeys, UIDefaults
from .plist_manager import PropertylistManager


class PatcherClient:
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
        enable_installomator: bool = True,
        ui_config: dict | None = None,
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
        :param enable_installomator: If False, :attr:`api` is ``None`` and
            Installomator-label matching (now sourced from the Patcher
            API catalog) is skipped. Kept under the legacy name for
            backward compatibility with existing CLI flags.
        :type enable_installomator: bool
        :param ui_config: Optional dict of UI settings (header text,
            footer, font paths, header color, etc.) for PDF/HTML report
            styling. Defaults to :class:`UIDefaults` values.
        :type ui_config: dict | None
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

        self._config = config
        self.debug = debug
        self.jamf = JamfClient(config=config, concurrency=concurrency)
        self.data = DataManager(disable_cache=disable_cache)
        self.api = PatcherAPIClient(max_concurrency=concurrency) if enable_installomator else None
        self.ui_config = ui_config if ui_config is not None else UIDefaults().model_dump()

    @classmethod
    def from_state(cls, **overrides: Any) -> "PatcherClient":
        """
        Construct a ``PatcherClient`` using state already persisted on this Mac.

        Reads Jamf credentials from the macOS keychain, UI customization
        from the property list, and the ``enable_installomator`` toggle.
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
        plist = PropertylistManager()
        ui_settings = plist.get("UserInterfaceSettings")
        enable_installomator = bool(plist.get("enable_installomator"))

        kwargs: dict[str, Any] = {
            "config": ConfigManager(),
            "enable_installomator": enable_installomator,
        }
        if ui_settings:
            kwargs["ui_config"] = ui_settings
        kwargs.update(overrides)

        return cls(**kwargs)

    async def fetch_patches(
        self,
        *,
        match_installomator: bool = True,
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
            ``enable_installomator=False`` was passed at construction time.
        :type match_installomator: bool
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
        policies = await self.jamf.get_policies()
        titles = await self.jamf.get_summaries(policies)

        if match_installomator and self.api is not None:
            await match_titles(titles, jamf=self.jamf, api=self.api)

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
        criteria: FilterCriteria | str,
        *,
        threshold: float | None = 70.0,
        top_n: int | None = None,
    ) -> list[PatchTitle]:
        """
        Filter and sort patch titles by a named criterion. The library
        equivalent of the CLI's ``analyze`` subcommand.

        Accepts either a :class:`~patcher.core.analyze.FilterCriteria` enum value or a CLI-style
        string (e.g. ``"most-installed"``, ``"below-threshold"``). String
        inputs are normalized via :meth:`~patcher.core.analyze.FilterCriteria.from_cli`.

        :param titles: Patch titles to analyze. Typically the output of
            :meth:`fetch_patches`.
        :type titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :param criteria: The filtering/sorting criterion. See
            :class:`~patcher.core.analyze.FilterCriteria` for available values.
        :type criteria: :class:`~patcher.core.analyze.FilterCriteria` | str
        :param threshold: Completion-percent threshold for ``below_threshold``
            criterion. Ignored by other criteria. Defaults to 70.0.
        :type threshold: float | None
        :param top_n: If provided, return at most ``top_n`` results. The
            ``below_threshold`` and ``zero_completion`` criteria ignore this
            (they return all matching titles).
        :type top_n: int | None
        :return: Filtered + sorted list of ``PatchTitle`` objects.
        :rtype: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :raises PatcherError: If ``criteria`` is not a recognized value.
        """
        if isinstance(criteria, str):
            criteria = FilterCriteria.from_cli(criteria)

        # Analyzer reads from data_manager.titles; stash the caller's list
        # there so the existing filter_titles logic can run without a refactor.
        # data.titles is a documented public setter, safe to assign to.
        self.data.titles = titles

        analyzer = Analyzer(self.data)
        return analyzer.filter_titles(criteria, threshold=threshold, top_n=top_n)

    async def analyze_excel(
        self,
        excel_path: str | Path,
        criteria: FilterCriteria | str,
        *,
        threshold: float | None = 70.0,
        top_n: int | None = None,
    ) -> list[PatchTitle]:
        """
        Filter and sort patch titles loaded from a saved Excel report.

        Library equivalent of ``patcherctl analyze --excel-file``. The Excel
        file is loaded into a fresh DataFrame, hydrated into ``PatchTitle``
        objects, and filtered exactly like :meth:`analyze`.

        :param excel_path: Path to a previously-exported Patcher Excel report.
        :type excel_path: str | :class:`pathlib.Path`
        :param criteria: Filter criterion (enum or CLI string).
        :type criteria: :class:`~patcher.core.analyze.FilterCriteria` | str
        :param threshold: Completion-percent cutoff for ``below_threshold``.
        :type threshold: float | None
        :param top_n: Optional result cap. Ignored by ``below_threshold`` and
            ``zero_completion``.
        :type top_n: int | None
        :return: Filtered + sorted titles loaded from the Excel file.
        :rtype: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :raises PatcherError: If the file is missing, empty, or unparseable.
        """
        if isinstance(criteria, str):
            criteria = FilterCriteria.from_cli(criteria)

        analyzer = Analyzer(excel_path=excel_path, data_manager=self.data)
        return analyzer.filter_titles(criteria, threshold=threshold, top_n=top_n)

    async def analyze_trend(
        self,
        criteria: TrendCriteria | str,
        *,
        save_to: str | Path | None = None,
    ):
        """
        Compute trend analysis across every cached patch dataset.

        Library equivalent of ``patcherctl analyze --all-time --criteria``.
        Reads every cached snapshot in the data cache and builds a trend
        DataFrame keyed on the requested criterion.

        :param criteria: Trend criterion (enum or CLI string, e.g.
            ``"patch-adoption"``, ``"release-frequency"``,
            ``"completion-trends"``).
        :type criteria: :class:`~patcher.core.analyze.TrendCriteria` | str
        :param save_to: Optional path. When provided, the trend DataFrame is
            also written to disk as HTML. Parent directories are created if
            needed.
        :type save_to: str | ~pathlib.Path | None
        :return: Trend results as a ~pandas.DataFrame. Empty if no
            data is available for the requested criterion.
        :rtype: ~pandas.DataFrame
        """
        if isinstance(criteria, str):
            criteria = TrendCriteria.from_cli(criteria)

        analyzer = Analyzer(self.data)
        trend_df = analyzer.timelapse(criteria)

        if save_to is not None and not trend_df.empty:
            save_to_path = Path(save_to)
            save_to_path.parent.mkdir(parents=True, exist_ok=True)
            trend_df.to_html(save_to_path, index=False)

        return trend_df

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
        Export patch titles to one or more report formats. Convenience
        wrapper around ``self.data.export``.

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
            Falls back to :attr:`~patcher.core.models.ui.UIDefaults.header_color` when ``None``.
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
        return await self.data.export(
            patch_titles=titles,
            output_dir=output_dir,
            report_title=report_title
            or self.ui_config.get(UIConfigKeys.HEADER.value, "Patch Report"),
            analysis=analysis,
            date_format=date_format,
            formats=formats,
            header_color=header_color,
            device_reports=device_reports,
        )

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
            return

        if self._config.in_memory_mode:
            raise PatcherError(
                f"reset(kind={kind!r}) requires keychain-backed credentials; "
                "this client was constructed with in-memory credentials.",
            )

        plist = PropertylistManager()

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
            plist.remove("UserInterfaceSettings")
            return

        if kind == "full":
            self._config.reset_config()
            plist.remove("UserInterfaceSettings")
            plist.remove("setup_completed")
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
