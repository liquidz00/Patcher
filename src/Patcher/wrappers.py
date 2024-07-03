import aiohttp
import plistlib
import shutil
import click
import os
import time

from configparser import ConfigParser
from functools import wraps
from typing import Callable
from pydantic import ValidationError
from src.Patcher.model.models import AccessToken
from src.Patcher.client.config_manager import ConfigManager
from src.Patcher.client.ui_manager import UIConfigManager
from src.Patcher.client.token_manager import TokenManager
from src.Patcher import exceptions, logger

# Logging
logthis = logger.setup_child_logger("wrappers", __name__)


# Automatic checking/refreshing of AccessToken
def check_token(func: Callable):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        instance = args[0]
        token_manager = instance.token_manager
        config = instance.config
        log = instance.log

        try:
            config.attach_client()
        except ValidationError as e:
            log.error(f"Failed validation: {e}")
            raise click.Abort()

        # Check if token is valid
        log.debug("Checking bearer token validity")
        if not token_manager.token_valid():
            log.warn("Bearer token is invalid, attempting refresh...")
            try:
                token = await token_manager.fetch_token()
                if token is None:
                    log.error("Token refresh returned None")
                    raise exceptions.TokenFetchError(
                        reason="Token refresh returned None"
                    )
                else:
                    log.info("Token successfully refreshed.")
            except aiohttp.ClientError as token_refresh_error:
                log.error(f"Failed to refresh token: {token_refresh_error}")
                raise exceptions.TokenFetchError(reason=token_refresh_error)
        else:
            log.debug("Bearer token passed validity checks.")

        # Ensure token has proper lifetime duration
        log.debug("Verifying token lifetime is greater than 5 minutes")
        token_lifetime = token_manager.check_token_lifetime()
        if token_lifetime:
            log.debug("Token lifetime verified successfully.")
        elif token_lifetime is False:
            log.error(
                "Bearer token lifetime is too short. Review the Patcher Wiki for instructions to increase the token's lifetime."
            )
            raise exceptions.TokenLifetimeError(
                lifetime=instance.token.seconds_remaining
            )
        else:
            log.debug("Token lifetime is at least 5 minutes. Continuing...")

        # Proceed with original function
        return await func(*args, **kwargs)

    return wrapper


# Welcome messages
greet = "Thanks for downloading Patcher!\n"

welcome_message = """It looks like this is your first time using the tool. We will guide you through the initial setup to get you started.

The setup assistant will prompt you for your Jamf URL, a client ID and a client secret. A bearer token will be generated for you and saved to your keychain.
Once the token has been retrieved and saved, you will be prompted to enter in the header and footer text for PDF reports, should you choose to generate them.

For more information, visit our project wiki: https://github.com/liquidz00/Patcher/wiki

"""
contribute = "Want to contribute? We'd welcome it! Submit a feature request on the repository and we will reach out as soon as possible!\n"


def first_run(func: Callable):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        logthis.debug("Initializing first_run check")
        config = ConfigManager()
        token_manager = TokenManager(config)
        ui_config = UIConfigManager()

        plist_path = os.path.expanduser(
            "~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist"
        )

        logthis.debug("Checking for presence of .plist file")
        first_run_done = False
        if os.path.exists(plist_path):
            try:
                with open(plist_path, "rb") as fp:
                    plist_data = plistlib.load(fp)
                    first_run_done = plist_data.get("first_run_done", False)
            except Exception as e:
                logthis.error(f"Error reading plist file: {e}")
                raise exceptions.PlistError(path=plist_path)

        if not first_run_done:
            logthis.info(
                f"Detected first status as {first_run_done}. Starting setup assistant..."
            )
            click.echo(click.style(greet, fg="cyan", bold=True))
            click.echo(click.style(welcome_message, fg="white"), nl=False)
            click.echo(click.style(contribute, fg="yellow"))
            # Prompt end user to proceed when ready, exit otherwise
            proceed = click.confirm("Ready to proceed?", default=False)
            if not proceed:
                click.echo("We'll be ready when you are!")
            else:
                api_url = click.prompt("Enter your Jamf Pro URL")
                api_client_id = click.prompt("Enter your API Client ID")
                api_client_secret = click.prompt("Enter your API Client Secret")

                # Store credentials
                config.set_credential("URL", api_url)
                config.set_credential("CLIENT_ID", api_client_id)
                config.set_credential("CLIENT_SECRET", api_client_secret)

                # Wait a short time to ensure creds are saved
                time.sleep(3)

                # Generate bearer token and save it
                token = await token_manager.fetch_token()

                if token and isinstance(token, AccessToken):
                    token_manager.save_token(token)

                    header_text = click.prompt(
                        "Enter the Header Text to use on PDF reports"
                    )
                    footer_text = click.prompt(
                        "Enter the Header Text to use on PDF reports"
                    )

                    use_custom_font = click.confirm(
                        "Would you like to use a custom font?", default=False
                    )
                    font_dir = os.path.join(ui_config.user_config_dir, "fonts")
                    os.makedirs(font_dir, exist_ok=True)

                    if use_custom_font:
                        font_name = click.prompt(
                            "Enter the custom font name", default="CustomFont"
                        )
                        font_regular_src_path = click.prompt(
                            "Enter the path to the regular font file"
                        )
                        font_bold_src_path = click.prompt(
                            "Enter the path to the bold font file"
                        )
                        font_regular_dest_path = os.path.join(
                            font_dir, os.path.basename(font_regular_src_path)
                        )
                        font_bold_dest_path = os.path.join(
                            font_dir, os.path.basename(font_bold_src_path)
                        )

                        # Copy files
                        shutil.copy(font_regular_src_path, font_regular_dest_path)
                        shutil.copy(font_bold_src_path, font_bold_dest_path)
                    else:
                        font_name = "Assistant"
                        font_regular_dest_path = os.path.join(
                            font_dir, "Assistant-Regular.ttf"
                        )
                        font_bold_dest_path = os.path.join(
                            font_dir, "Assistant-Bold.ttf"
                        )

                    config_parser = ConfigParser()
                    config_parser.read(ui_config.user_config_path)

                    if "UI" not in config_parser.sections():
                        config_parser.add_section("UI")
                    config_parser.set("UI", "HEADER_TEXT", header_text)
                    config_parser.set("UI", "FOOTER_TEXT", footer_text)
                    config_parser.set("UI", "FONT_NAME", font_name)
                    config_parser.set("UI", "FONT_REGULAR_PATH", font_regular_dest_path)
                    config_parser.set("UI", "FONT_BOLD_PATH", font_bold_dest_path)

                    with open(ui_config.user_config_path, "w") as configfile:
                        config_parser.write(configfile)

                    plist_data = {"first_run_done": True}
                    try:
                        os.makedirs(os.path.dirname(plist_path), exist_ok=True)
                        with open(plist_path, "wb") as fp:
                            plistlib.dump(plist_data, fp)
                    except Exception as e:
                        logthis.error(f"Error writing to plist file: {e}")
                        raise exceptions.PlistError(path=plist_path)
                else:
                    logthis.error("Failed to fetch a valid token!")
                    raise click.Abort()
        else:
            logthis.debug("First run already completed.")
        return await func(*args, **kwargs)

    return wrapper
