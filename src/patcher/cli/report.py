"""CLI-side report orchestration.

Holds the animation-driven workflow that drives the ``patcherctl export``
command. Pulled out of :class:`patcher.core.report_manager.ReportManager`
so the core class stays free of ``asyncclick`` and the animation spinner;
library callers wire the building blocks themselves (or use
:class:`~patcher.core.patcher_client.PatcherClient` and call its
collaborators) and skip the terminal presentation entirely.
"""

from pathlib import Path

import asyncclick as click

from ..core.exceptions import APIResponseError, PatcherError
from ..core.patcher_client import PatcherClient
from .animation import Animation


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
    spinner and prints a success banner on completion — both CLI-presentation
    concerns that don't belong in the core layer. Library callers should
    invoke ``patcher.jamf`` / ``patcher.data`` / ``patcher.installomator``
    directly instead.

    :param patcher: Pre-configured ``PatcherClient`` carrying the
        ``JamfClient``, ``DataManager``, ``InstallomatorClient``, and
        ``ReportManager`` helpers.
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
    report = patcher.report
    animation = Animation(enable_animation=not report.debug)
    log = report.log

    async with animation.error_handling():
        log.debug("Starting report generation process.")
        output_path = report._validate_directory(path)

        log.debug("Attempting to retrieve policy IDs.")
        await animation.update_msg("Retrieving policy IDs from Jamf...")
        try:
            patch_ids = await patcher.jamf.get_policies()
            log.info(f"Retrieved policy IDs for {len(patch_ids)} policies.")
        except APIResponseError as e:
            log.error(f"Unable to obtain policy IDs from Jamf instance. Details: {e}")
            raise PatcherError(
                "Failed to retrieve policy IDs from Jamf instance.", error_msg=str(e)
            )

        log.debug("Attempting to retrieve patch summaries.")
        await animation.update_msg("Retrieving patch summaries from Jamf...")
        try:
            patch_reports = await patcher.jamf.get_summaries(patch_ids)
            log.info(f"Received policy summaries for {len(patch_reports)} policies.")
        except APIResponseError as e:
            log.error(f"Unable to fetch patch summaries from Jamf instance. Details: {e}")
            raise PatcherError(
                "Failed to retrieve patch summaries from Jamf instance.", error_msg=str(e)
            )

        if sort:
            await animation.update_msg("Sorting reports...")
            patch_reports = await report._sort(patch_reports, sort)

        if omit:
            await animation.update_msg("Omitting recent releases...")
            patch_reports = await report._omit(patch_reports)

        if ios:
            await animation.update_msg("Including iOS info...")
            patch_reports = await report._ios(patch_reports)

        if enable_iom and patcher.installomator is not None:
            await animation.update_msg("Identifying Installomator support for titles...")
            try:
                await patcher.installomator.match(patch_reports)
            except APIResponseError as e:
                if getattr(e, "not_found", False):
                    log.warning(f"One or more patch titles were not found: {e}")
                else:
                    log.error(f"An API error occurred while matching patch titles: {e}")

        device_reports = None
        if device_details:
            await animation.update_msg("Fetching per-title patch reports...")
            title_ids = [patch.title_id for patch in patch_reports]
            device_reports = await patcher.jamf.get_title_reports(title_ids)

        await animation.update_msg("Generating reports...")
        await patcher.data.export(
            patch_titles=patch_reports,
            output_dir=output_path,
            report_title=report_title,
            analysis=False,
            formats=formats,
            date_format=date_format,
            header_color=header_color,
            device_reports=device_reports,
        )

    # Manually stop animation so the success message renders cleanly
    animation.stop_event.set()
    log.info(f"{len(patch_reports)} patch reports saved successfully to {output_path}.")
    click.echo(click.style(f"\r✅ Success! Reports saved to {output_path}", bold=True, fg="green"))
