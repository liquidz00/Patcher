"""
CLI orchestration helpers.

The functions the asyncclick entry point and commands lean on but that aren't
commands themselves: argument parsing, cache setup, the shared ``DataManager``
accessor, process-hook installation, and the ``export`` report-generation
workflow. Presentation (console, styles, renderers, logging) lives in
:mod:`patcher.cli._console`.
"""

import inspect
import os
import re
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

import asyncclick as click

from ..clients.installomator import InstallomatorClient
from ..core.analyze import append_ios_status, omit_recent, sort_titles
from ..core.data_manager import DataManager
from ..core.exceptions import APIResponseError, InstallomatorWarning, PatcherError
from ..core.logger import LogMe
from ..core.matching import match_titles
from ..core.patcher_client import PatcherClient
from ._console import SUCCESS_STYLE, console, install_terminal_excepthook, progress_bar

_SINCE_PATTERN = re.compile(r"^(\d+)([dhw])$")  # short window: 30d / 24h / 1w


def warning_format(message, category, filename, lineno, file=None, line=None):
    """Terse one-line warnings formatter (``Category: message``) for CLI runs."""
    return f"{category.__name__}: {message}\n"


def parse_since(value: str) -> timedelta:
    """Parse a short window like ``'30d'``, ``'24h'``, ``'1w'`` into a timedelta."""
    match = _SINCE_PATTERN.match(value.strip().lower())
    if not match:
        raise PatcherError(
            "Invalid --since format. Use a number followed by 'd', 'h', or 'w' (e.g. '30d', '24h', '1w').",
            received=value,
        )
    quantity, unit = int(match.group(1)), match.group(2)
    units = {"d": "days", "h": "hours", "w": "weeks"}
    return timedelta(**{units[unit]: quantity})


def parse_iso_date(value: str) -> date:
    """Parse ``'2026-05-17'``-style ISO date strings."""
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise PatcherError(
            "Invalid date format. Use ISO YYYY-MM-DD (e.g. '2026-05-17').",
            received=value,
            error_msg=str(exc),
        )


def initialize_cache(cache_dir: Path) -> None:
    """
    Ensures the cache directory exists while avoiding creating system-managed directories.

    :param cache_dir: The full path to the cache directory (e.g., ~/Library/Caches/Patcher).
    :type cache_dir: ~pathlib.Path
    """
    log = LogMe(inspect.currentframe().f_code.co_name)

    parent_dir = cache_dir.parent
    if not parent_dir.exists():
        log.warning(f"Parent directory {parent_dir} does not exist. Skipping cache setup.")
        return

    try:
        cache_dir.mkdir(parents=False, exist_ok=True)
        log.debug(f"Cache directory initialized at {cache_dir}")
    except OSError as err:
        log.warning(f"Failed to initialize cache directory. Details: {err}")
        return


def get_data_manager(ctx: click.Context) -> DataManager:
    """
    Lazily initializes and returns the shared ``DataManager`` instance.

    This ensures consistent handling of ``DataManager`` objects. Inconsistent handling of said objects could lead to inaccurate patch reports or false errors getting raised.

    :param ctx: Click context object.
    :type ctx: `click.Context <https://click.palletsprojects.com/en/stable/api/#click.Context>`_
    :return: The initialized ``DataManager`` instance.
    :rtype: :class:`~patcher.core.data_manager.DataManager`
    """
    if "data_manager" not in ctx.obj or ctx.obj.get("data_manager") is None:
        ctx.obj["data_manager"] = DataManager(disable_cache=ctx.obj.get("disable_cache", False))
    return ctx.obj["data_manager"]


def _install_cli_process_hooks() -> None:
    """
    Apply process-wide side effects scoped to a CLI invocation.

    Kept inside the ``cli()`` callback rather than at module import time so
    importing ``patcher.cli.setup`` (or anything else under ``patcher.cli``)
    from library code does not mutate ``sys.excepthook`` or the global
    warnings filter as a side effect.
    """
    install_terminal_excepthook()
    warnings.simplefilter("always", InstallomatorWarning)
    warnings.formatwarning = warning_format
    # One-time sweep of the retired on-disk Installomator label cache (no-op once gone).
    InstallomatorClient.purge_legacy_disk_cache()


def _validate_output_dir(path: str | Path) -> str:
    """Expand ``path`` and ensure a ``Patch-Reports`` subdirectory exists under it."""
    output_path = os.path.expanduser(path)
    try:
        os.makedirs(output_path, exist_ok=True)
        reports_dir = os.path.join(output_path, "Patch-Reports")
        os.makedirs(reports_dir, exist_ok=True)
        return reports_dir
    except (OSError, PermissionError) as e:
        raise PatcherError(
            "Failed to create Patch Reports directory path.",
            path=output_path,
            error_msg=str(e),
        )


async def process_reports(
    patcher: PatcherClient,
    *,
    path: str | Path,
    formats: set[str],
    sort: str | None,
    omit: bool,
    ios: bool,
    report_title: str,
    header_color: str,
    date_format: str = "%B %d %Y",
    enable_iom: bool = True,
    enable_homebrew: bool = False,
    device_details: bool = False,
) -> None:
    """
    Drive the full CLI report-generation workflow against a configured
    :class:`~patcher.core.patcher_client.PatcherClient`.

    Wraps the orchestration in a Rich status spinner and prints a success
    banner on completion. Both are CLI-presentation concerns that don't
    belong in the core layer. Library callers should call ``patcher.jamf``,
    the transforms in :mod:`patcher.core.analyze`, and ``patcher.export(...)``
    directly.

    :param patcher: Pre-configured ``PatcherClient`` carrying the
        ``JamfClient``, ``DataManager``, and ``InstallomatorClient`` collaborators.
    :type patcher: :class:`~patcher.core.patcher_client.PatcherClient`
    :param path: Output directory for the generated reports.
    :type path: str | ~pathlib.Path
    :param formats: Export formats to write (``excel``, ``html``, ``pdf``, ``json``).
    :type formats: set[str]
    :param sort: Optional column name to sort by (e.g. ``released``).
    :type sort: str | None
    :param omit: If True, drop patches released within the last 48 hours.
    :type omit: bool
    :param ios: If True, append iOS device status to the report.
    :type ios: bool
    :param report_title: Title to embed in the report header.
    :type report_title: str
    :param header_color: Hex color for the HTML report header.
    :type header_color: str
    :param date_format: ``datetime.strftime`` format string for date columns.
    :type date_format: str
    :param enable_iom: If False, skip Installomator label matching.
    :type enable_iom: bool
    :param enable_homebrew: If True, also match titles against the Homebrew
        Cask source, populating
        :attr:`~patcher.core.models.patch.PatchTitle.homebrew_cask`. Rides on
        the same match pass as Installomator, so it is a no-op when
        ``enable_iom`` is False.
    :type enable_homebrew: bool
    :param device_details: If True, include per-title device sheets in Excel export.
    :type device_details: bool
    """
    with progress_bar(disable=patcher.debug) as progress:
        task = progress.add_task("Initializing...", total=None)
        output_path = _validate_output_dir(path)

        progress.update(task, description="Retrieving policy IDs from Jamf...")
        try:
            patch_ids = await patcher.jamf.get_policies()
        except APIResponseError as e:
            raise PatcherError(
                "Failed to retrieve policy IDs from Jamf instance.", error_msg=str(e)
            )

        progress.update(task, description="Retrieving patch summaries from Jamf...")
        try:
            patch_reports = await patcher.jamf.get_summaries(patch_ids)
        except APIResponseError as e:
            raise PatcherError(
                "Failed to retrieve patch summaries from Jamf instance.", error_msg=str(e)
            )

        if sort:
            progress.update(task, description="Sorting reports...")
            patch_reports = await sort_titles(patch_reports, sort)

        if omit:
            progress.update(task, description="Omitting recent releases...")
            patch_reports = await omit_recent(patch_reports)

        if ios:
            progress.update(task, description="Including iOS info...")
            patch_reports = await append_ios_status(patch_reports, patcher.jamf)

        if enable_iom and patcher.api is not None:
            msg = (
                "Identifying Installomator and Homebrew support for titles..."
                if enable_homebrew
                else "Identifying Installomator support for titles..."
            )
            progress.update(task, description=msg, total=len(patch_reports), completed=0)

            def on_match(done: int, total: int) -> None:
                progress.update(task, completed=done, total=total)

            try:
                await match_titles(
                    patch_reports,
                    jamf=patcher.jamf,
                    api=patcher.api,
                    include_homebrew=enable_homebrew,
                    progress_callback=on_match,
                )
            except APIResponseError as e:
                if not getattr(e, "not_found", False):
                    raise
            progress.update(task, total=None)  # back to indeterminate for the remaining steps

        device_reports = None
        if device_details:
            progress.update(task, description="Fetching per-title patch reports...")
            title_ids = [patch.title_id for patch in patch_reports]
            device_reports = await patcher.jamf.get_title_reports(title_ids)

        progress.update(task, description="Generating reports...")
        await patcher.export(
            patch_reports,
            output_dir=output_path,
            formats=formats,
            report_title=report_title,
            date_format=date_format,
            header_color=header_color,
            device_reports=device_reports,
        )

    console.print(f"✅ Success! Reports saved to {output_path}", style=SUCCESS_STYLE)
