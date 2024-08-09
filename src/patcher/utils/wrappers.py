from functools import wraps
from typing import Any, Callable

import aiohttp
from pydantic import ValidationError

from patcher.utils import exceptions, logger

# Logging
logthis = logger.setup_child_logger("wrappers", __name__)


# Automatic checking/refreshing of AccessToken
def check_token(func: Callable) -> Any:
    """
    Decorator that ensures the validity of an access token before executing a function.

    The ``check_token`` decorator performs several key tasks before the decorated
    function is executed:

    1. It validates the configuration of the token manager's client.
    2. It checks if the current access token is valid. If the token is invalid,
       it attempts to refresh the token.
    3. It ensures that the token has a sufficient remaining lifetime (at least 5 minutes).
       If the token's lifetime is insufficient, it raises a ``TokenLifetimeError``.

    This decorator is intended for use with asynchronous methods that require
    a valid and sufficiently long-lived access token to interact with the Jamf API.

    :param func: The asynchronous function to be decorated.
    :type func: Callable
    :raises pydantic.ValidationError: If the configuration validation fails.
    :raises TokenFetchError: If token refresh fails or returns ``None``.
    :raises TokenLifetimeError: If the token's remaining lifetime is too short.
    :return: The result of the decorated function.
    :rtype: Any
    """

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
            raise

        # Check if token is valid
        log.debug("Checking bearer token validity")
        if not token_manager.token_valid():
            log.warning("Bearer token is invalid, attempting refresh...")
            try:
                token = await token_manager.fetch_token()
                if token is None:
                    log.error("Token refresh returned None")
                    raise exceptions.TokenFetchError(reason="Token refresh returned None")
                else:
                    log.info("Token successfully refreshed.")
            except aiohttp.ClientError as token_refresh_error:
                log.error(f"Failed to refresh token: {token_refresh_error}")
                raise exceptions.TokenFetchError(reason=str(token_refresh_error))
        else:
            log.debug("Bearer token passed validity checks.")

        # Ensure token has proper lifetime duration
        log.debug("Verifying token lifetime is greater than 5 minutes")
        token_lifetime = token_manager.check_token_lifetime()
        if token_lifetime:
            log.debug("Token lifetime verified successfully.")
        elif token_lifetime is False:
            log.error(
                "Bearer token lifetime is too short. Review the patcher Wiki for instructions to increase the token's lifetime."
            )
            raise exceptions.TokenLifetimeError(lifetime=instance.token.seconds_remaining)
        else:
            log.debug("Token lifetime is at least 5 minutes. Continuing...")

        # Proceed with original function
        return await func(*args, **kwargs)

    return wrapper
