import aiohttp
from functools import wraps
from src import logger
from datetime import datetime
from typing import List, AnyStr, Dict, Optional, Callable
from src.client.token_manager import TokenManager
from src import exceptions

# Logging
logthis = logger.setup_child_logger("helpers", __name__)

# Automatic checking/refreshing of AccessToken
def check_token(func: Callable):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        instance = args[0]
        token_manager = instance.token_manager
        log = instance.log

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
        try:
            token_lifetime = await token_manager.check_token_lifetime()
            log.info("Token lifetime verified successfully.")
        except aiohttp.ClientResponseError as e:
            log.error(
                f"Received unauthorized response checking token lifetime. API client may not have sufficient privileges."
            )
            raise exceptions.APIPrivilegeError(reason=e)
        if not token_lifetime:
            log.error(
                "Bearer token lifetime is too short. Review the Patcher Wiki for instructions to increase the token's lifetime.",
            )
            raise exceptions.TokenLifetimeError(lifetime=instance.config.get_credential("TOKEN_EXPIRATION"))
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
