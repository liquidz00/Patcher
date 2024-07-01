import aiohttp
import os
import plistlib
import click
import time
from functools import wraps
from datetime import datetime
from typing import List, AnyStr, Dict, Optional, Callable
from configparser import ConfigParser
from src.Patcher.client.token_manager import TokenManager
from src.Patcher.client.config_manager import ConfigManager
from src.Patcher.model.models import AccessToken
from pydantic import ValidationError
from src.Patcher import exceptions, logger

# Logging
logthis = logger.setup_child_logger("helpers", __name__)


# Check for API Client credentials
def cred_check(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        config = ConfigManager()
        token_manager = TokenManager(config)
        try:
            config.attach_client()
        except ValidationError as e:
            logthis.error(f"JamfClient validation failed: {e}")
            raise click.Abort()

        plist_path = os.path.expanduser(
            "~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist"
        )

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
                if use_custom_font:
                    font_name = click.prompt(
                        "Enter the custom font name", default="CustomFont"
                    )
                    font_regular_path = click.prompt(
                        "Enter the path to the regular font file"
                    )
                    font_bold_path = click.prompt(
                        "Enter the path to the bold font file"
                    )
                else:
                    font_name = "Assistant"
                    font_regular_path = "fonts/Assistant-Regular.ttf"
                    font_bold_path = "fonts/Assistant-Bold.ttf"

                user_config_dir = os.path.expanduser(
                    "~/Library/Application Support/Patcher"
                )
                user_config_path = os.path.join(user_config_dir, "config.ini")

                config_parser = ConfigParser()
                if os.path.exists(user_config_path):
                    config_parser.read(user_config_path)

                if "UI" not in config_parser.sections():
                    config_parser.add_section("UI")
                config_parser.set("UI", "HEADER_TEXT", header_text)
                config_parser.set("UI", "FOOTER_TEXT", footer_text)
                config_parser.set("UI", "FONT_NAME", font_name)
                config_parser.set("UI", "FONT_REGULAR_PATH", font_regular_path)
                config_parser.set("UI", "FONT_BOLD_PATH", font_bold_path)

                os.makedirs(user_config_dir, exist_ok=True)
                with open(user_config_path, "w") as configfile:
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
        elif not token_lifetime:
            log.error(
                "Bearer token lifetime is too short. Review the Patcher Wiki for instructions to increase the token's lifetime.",
            )
            raise exceptions.TokenLifetimeError(
                lifetime=instance.token.seconds_remaining
            )
        else:
            log.debug("Token lifetime is at least 5 minutes. Continuing...")

        # Proceed with original function
        return await func(*args, **kwargs)

    return wrapper


# Format UTC time
def convert_timezone(utc_time_str: AnyStr) -> Optional[AnyStr]:
    """
    Converts a UTC time string to a formatted string without timezone information.

    :param utc_time_str: UTC time string in ISO 8601 format.
    :type utc_time_str: AnyStr
    :return: Formatted time string or error message.
    :rtype: AnyStr
    """
    try:
        utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S%z")
        time_str = utc_time.strftime("%b %d %Y")
        return time_str
    except ValueError as e:
        logthis.error(f"Invalid time format provided. Details: {e}")
        return None


# iOS Functionality - Calculate amount of devices on latest version
def calculate_ios_on_latest(
    device_versions: List[Dict[AnyStr, AnyStr]],
    latest_versions: List[Dict[AnyStr, AnyStr]],
) -> Optional[List[Dict]]:
    """
    Calculates the amount of enrolled devices are on the latest version of their respective operating system.

    :param device_versions: A list of nested dictionaries containing devices and corresponding operating system versions
    :type device_versions: List[Dict[AnyStr, AnyStr]]
    :param latest_versions: A list of latest available iOS versions, from SOFA feed
    :type latest_versions: List[Dict[AnyStr, AnyStr]]
    :return: A list with calculated data per iOS version
    """
    if not device_versions or not latest_versions:
        logthis.error("Error calculating iOS Versions. Received None instead of a List")
        return None

    latest_versions_dict = {lv.get("OSVersion"): lv for lv in latest_versions}

    version_counts = {
        version: {"count": 0, "total": 0} for version in latest_versions_dict.keys()
    }

    for device in device_versions:
        device_os = device.get("OS")
        major_version = device_os.split(".")[0]
        if major_version in version_counts:
            version_counts[major_version]["total"] += 1
            if device_os == latest_versions_dict[major_version]["ProductVersion"]:
                version_counts[major_version]["count"] += 1

    mapped = []
    for version, counts in version_counts.items():
        if counts["total"] > 0:
            completion_percent = round((counts["count"] / counts["total"]) * 100, 2)
            mapped.append(
                {
                    "software_title": f"iOS {latest_versions_dict[version]['ProductVersion']}",
                    "patch_released": latest_versions_dict[version]["ReleaseDate"],
                    "hosts_patched": counts["count"],
                    "missing_patch": counts["total"] - counts["count"],
                    "completion_percent": completion_percent,
                    "total_hosts": counts["total"],
                }
            )

    return mapped
