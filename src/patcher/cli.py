import asyncio
from typing import AnyStr, Optional

import asyncclick as click

from .__about__ import __version__
from .client.api_client import ApiClient
from .client.config_manager import ConfigManager
from .client.report_manager import ReportManager
from .client.setup import Setup
from .client.token_manager import TokenManager
from .client.ui_manager import UIConfigManager
from .models.reports.excel_report import ExcelReport
from .models.reports.pdf_report import PDFReport
from .utils.animation import Animation
from .utils.exceptions import PatcherError
from .utils.logger import LogMe

DATE_FORMATS = {
    "Month-Year": "%B %Y",  # April 2024
    "Month-Day-Year": "%B %d %Y",  # April 21 2024
    "Year-Month-Day": "%Y %B %d",  # 2024 April 21
    "Day-Month-Year": "%d %B %Y",  # 16 April 2024
    "Full": "%A %B %d %Y",  # Thursday September 26 2013
}


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--debug",
    "-x",
    is_flag=True,
    default=False,
    help="Enable debug logging to see detailed debug messages.",
)
@click.option(
    "--custom-ca-file",
    type=click.Path(),
    required=False,
    help="Path to a custom CA file for SSL verification.",
)
@click.option(
    "--concurrency",
    type=click.INT,
    default=5,
    help="Set the maximum concurrency level for API calls.",
)
@click.pass_context
async def cli(
    ctx: click.Context, debug: bool, custom_ca_file: Optional[str], concurrency: Optional[int]
):
    ctx.ensure_object(dict)

    ctx.obj["DEBUG"] = debug
    ctx.obj["CA_FILE"] = custom_ca_file
    ctx.obj["CONCURRENCY"] = concurrency

    # Instance of config, add to context
    config_manager = ConfigManager()
    ctx.obj["CONFIG_MANAGER"] = config_manager

    # Instance of api, add to context
    # api = ApiClient(config=config_manager, custom_ca_file=custom_ca_file, concurrency=concurrency)
    # ctx.obj["API_CLIENT"] = api

    # Instance of UI, add to context
    ui_config = UIConfigManager()
    ctx.obj["UI_MANAGER"] = ui_config

    # Instance of token manager, add to context
    token_manager = TokenManager(config=config_manager)
    ctx.obj["TOKEN_MANAGER"] = token_manager

    # Instance of animation
    ctx.obj["ANIMATION"] = Animation(enable_animation=not debug)


@cli.command()
@click.option(
    "--reset",
    "-r",
    is_flag=True,
    default=False,
    help="Resets the UI elements in PDF reports, allowing to set new values.",
)
@click.pass_context
async def setup(ctx: click.Context, reset: bool):
    config = ctx.obj["CONFIG_MANAGER"]
    custom_ca_file = ctx.obj["CA_FILE"]
    concurrency = ctx.obj["CONCURRENCY"]
    api_client = ApiClient(config=config, concurrency=concurrency, custom_ca_file=custom_ca_file)
    token_manager = ctx.obj["TOKEN_MANAGER"]
    ui_manager = ctx.obj["UI_MANAGER"]
    setup_manager = Setup(
        config=config,
        ui_config=ui_manager,
        api_client=api_client,
        token_manager=token_manager,
        custom_ca_file=custom_ca_file,
    )

    log = LogMe(__name__, debug=ctx.obj["DEBUG"])
    animation = ctx.obj["ANIMATION"]

    async with animation.error_handling(log):
        if not setup_manager.completed:
            await setup_manager.prompt_method(animator=animation)
            click.echo(click.style(text="Setup has completed successfully!", fg="green", bold=True))
            click.echo("Patcher is now ready for use.")
            click.echo("For more information, visit the project docs: https://patcher.liquidzoo.io")
        elif reset:
            await animation.update_msg("Resetting elements...")
            await setup_manager.reset()
            click.echo(click.style(text="Reset has completed as expected!", fg="green", bold=True))
            return


@cli.command()
@click.option(
    "--path",
    "-p",
    type=click.Path(),
    required=True,
    help="Path to save the report(s)",
)
@click.option(
    "--pdf",
    "-f",
    is_flag=True,
    help="Generate a PDF report along with Excel spreadsheet",
)
@click.option(
    "--sort",
    "-s",
    type=click.STRING,
    required=False,
    help="Sort patch reports by a specified column.",
)
@click.option(
    "--omit",
    "-o",
    is_flag=True,
    help="Omit software titles with patches released in last 48 hours",
)
@click.option(
    "--date-format",
    "-d",
    type=click.Choice(list(DATE_FORMATS.keys()), case_sensitive=False),
    default="Month-Day-Year",
    help="Specify the date format for the PDF header from predefined choices.",
)
@click.option(
    "--ios",
    "-m",
    is_flag=True,
    help="Include the amount of enrolled mobile devices on the latest version of their respective OS.",
)
@click.pass_context
async def export(
    ctx: click.Context,
    path: AnyStr,
    pdf: bool,
    sort: Optional[AnyStr],
    omit: bool,
    date_format: AnyStr,
    ios: bool,
) -> None:
    debug = ctx.obj["DEBUG"]
    custom_ca_file = ctx.obj["CA_FILE"]
    concurrency = ctx.obj["CONCURRENCY"]
    log = LogMe(__name__, debug=debug)

    animation = ctx.obj["ANIMATION"]

    config = ctx.obj["CONFIG_MANAGER"]
    api_client = ApiClient(config, concurrency, custom_ca_file)
    ui_manager = ctx.obj["UI_MANAGER"]

    jamf_client = config.attach_client()
    if jamf_client is None:
        raise PatcherError(message="Invalid JamfClient configuration detected!")

    token_manager = ctx.obj["TOKEN_MANAGER"]
    api_client.jamf_client = jamf_client
    excel_report = ExcelReport()
    pdf_report = PDFReport(ui_manager)

    report_manager = ReportManager(
        config=config,
        token_manager=token_manager,
        api_client=api_client,
        excel_report=excel_report,
        pdf_report=pdf_report,
        ui_config=ui_manager,
        debug=debug,
    )

    actual_format = DATE_FORMATS[date_format]

    async with animation.error_handling(log):
        await report_manager.process_reports(path, pdf, sort, omit, ios, actual_format)


@cli.command()
@click.pass_context
async def analyze():
    pass


if __name__ == "__main__":
    asyncio.run(cli())
