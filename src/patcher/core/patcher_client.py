"""
Top-level class for Patcher's library use.

Composes the per-service clients (:class:`JamfClient`,
:class:`InstallomatorClient`) and data layer (:class:`DataManager`) into
a single object library callers instantiate. CLI users construct the
same object via the existing ``Setup`` flow, which populates a
:class:`ConfigManager` and hands it to ``PatcherClient`` through the
``config=`` argument.

For raw, lower-level access without ``PatcherClient``, see
:class:`patcher.client.jamf.JamfClient` (Jamf API directly) and
:class:`patcher.client.HTTPClient` (generic httpx with truststore).
"""

from pathlib import Path

from ..client.jamf import JamfClient
from .analyze import (
    Analyzer,
    FilterCriteria,
    append_ios_status,
    omit_recent,
    sort_titles,
)
from .config_manager import ConfigManager
from .data_manager import DataManager
from .exceptions import PatcherError
from .installomator import InstallomatorClient
from .logger import LogMe
from .models.patch import PatchTitle
from .models.ui import UIDefaults


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

        An in-memory :class:`ConfigManager` is built internally. No keyring
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
        :param enable_installomator: If False, :attr:`installomator` is
            ``None`` and Installomator label matching is skipped.
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
        self.installomator = (
            InstallomatorClient(concurrency=concurrency, api=self.jamf)
            if enable_installomator
            else None
        )
        self.ui_config = ui_config if ui_config is not None else UIDefaults().model_dump()

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
        Equivalent to manually chaining :meth:`jamf.get_policies`,
        :meth:`jamf.get_summaries`, :meth:`installomator.match`,
        :func:`~patcher.core.analyze.append_ios_status`,
        :func:`~patcher.core.analyze.omit_recent`, and
        :func:`~patcher.core.analyze.sort_titles`.

        :param match_installomator: If True (default), match each title to its
            Installomator label via :meth:`installomator.match`. No-op when
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

        if match_installomator and self.installomator is not None:
            await self.installomator.match(titles)

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

        Accepts either a :class:`FilterCriteria` enum value or a CLI-style
        string (e.g. ``"most-installed"``, ``"below-threshold"``). String
        inputs are normalized via :meth:`FilterCriteria.from_cli`.

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

    async def export(
        self,
        titles: list[PatchTitle],
        *,
        output_dir: str | Path,
        formats: set[str] | None = None,
        report_title: str | None = None,
        date_format: str = "%B %d %Y",
        header_color: str | None = "#6432bdff",
        analysis: bool = False,
        device_reports: dict[str, list] | None = None,
    ) -> dict[str, str]:
        """
        Export patch titles to one or more report formats. Convenience
        wrapper around :meth:`data.export`.

        :param titles: Patch titles to include in the report.
        :type titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :param output_dir: Directory to write report file(s) into.
        :type output_dir: str | Path
        :param formats: Set of format strings to emit. Defaults to all four:
            ``{"excel", "html", "pdf", "json"}``.
        :type formats: set[str] | None
        :param report_title: Title used in PDF/HTML headers. Defaults to the
            ``HEADER_TEXT`` value from this client's ``ui_config``.
        :type report_title: str | None
        :param date_format: Date format for PDF/HTML headers (strftime).
            Defaults to ``"%B %d %Y"``.
        :type date_format: str
        :param header_color: Hex color for the HTML report header background.
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
            report_title=report_title or self.ui_config.get("HEADER_TEXT", "Patch Report"),
            analysis=analysis,
            date_format=date_format,
            formats=formats,
            header_color=header_color,
            device_reports=device_reports,
        )

    async def aclose(self) -> None:
        """
        Release the underlying httpx connection pool.

        Idempotent. Safe to call multiple times. PatcherClient owns a single
        :class:`~patcher.client.jamf.JamfClient` (shared by
        :attr:`installomator` when present); closing it releases the pool
        for both collaborators.
        """
        await self.jamf.aclose()

    async def __aenter__(self) -> "PatcherClient":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.aclose()
