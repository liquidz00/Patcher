"""
CLI-side report orchestration.

Drives the ``patcherctl export`` workflow: wraps the patch-data pipeline
(fetch policies → fetch summaries → filter/sort → match Installomator
labels → export to disk) in an :class:`Animation` spinner and prints a
success banner. Library callers should use the underlying transforms in
:mod:`patcher.core.analyze` and call ``patcher.data.export(...)``
directly.
"""

import os
from pathlib import Path

import asyncclick as click

from ..core.analyze import append_ios_status, omit_recent, sort_titles
from ..core.exceptions import APIResponseError, PatcherError
from ..core.matching import match_titles
from ..core.patcher_client import PatcherClient
from .animation import Animation


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
    device_details: bool = False,
) -> None:
    """
    Drive the full CLI report-generation workflow against a configured
    :class:`~patcher.core.patcher_client.PatcherClient`.

    Wraps the orchestration in an :class:`~patcher.cli.animation.Animation`
    spinner and prints a success banner on completion. Both are CLI-presentation
    concerns that don't belong in the core layer. Library callers should call
    ``patcher.jamf``, the transforms in :mod:`patcher.core.analyze`, and
    ``patcher.data.export(...)`` directly.

    :param patcher: Pre-configured ``PatcherClient`` carrying the
        ``JamfClient``, ``DataManager``, and ``InstallomatorClient`` collaborators.
    :type patcher: :class:`~patcher.core.patcher_client.PatcherClient`
    :param path: Output directory for the generated reports.
    :type path: str | Path
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
    :param device_details: If True, include per-title device sheets in Excel export.
    :type device_details: bool
    """
    animation = Animation(enable_animation=not patcher.debug)

    async with animation.error_handling():
        output_path = _validate_output_dir(path)

        await animation.update_msg("Retrieving policy IDs from Jamf...")
        try:
            patch_ids = await patcher.jamf.get_policies()
        except APIResponseError as e:
            raise PatcherError(
                "Failed to retrieve policy IDs from Jamf instance.", error_msg=str(e)
            )

        await animation.update_msg("Retrieving patch summaries from Jamf...")
        try:
            patch_reports = await patcher.jamf.get_summaries(patch_ids)
        except APIResponseError as e:
            raise PatcherError(
                "Failed to retrieve patch summaries from Jamf instance.", error_msg=str(e)
            )

        if sort:
            await animation.update_msg("Sorting reports...")
            patch_reports = await sort_titles(patch_reports, sort)

        if omit:
            await animation.update_msg("Omitting recent releases...")
            patch_reports = await omit_recent(patch_reports)

        if ios:
            await animation.update_msg("Including iOS info...")
            patch_reports = await append_ios_status(patch_reports, patcher.jamf)

        if enable_iom and patcher.api is not None:
            await animation.update_msg("Identifying Installomator support for titles...")
            try:
                await match_titles(patch_reports, jamf=patcher.jamf, api=patcher.api)
            except APIResponseError as e:
                if not getattr(e, "not_found", False):
                    raise

        device_reports = None
        if device_details:
            await animation.update_msg("Fetching per-title patch reports...")
            title_ids = [patch.title_id for patch in patch_reports]
            device_reports = await patcher.jamf.get_title_reports(title_ids)

        await animation.update_msg("Generating reports...")
        await patcher.export(
            patch_reports,
            output_dir=output_path,
            formats=formats,
            report_title=report_title,
            date_format=date_format,
            header_color=header_color,
            device_reports=device_reports,
        )

    animation.stop_event.set()
    click.echo(click.style(f"\r✅ Success! Reports saved to {output_path}", bold=True, fg="green"))
