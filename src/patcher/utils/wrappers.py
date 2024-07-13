from functools import wraps
from typing import Callable

import aiohttp
import click
from pydantic import ValidationError

from patcher.utils import exceptions, logger

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
                    raise exceptions.TokenFetchError(reason="Token refresh returned None")
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
                "Bearer token lifetime is too short. Review the patcher Wiki for instructions to increase the token's lifetime."
            )
            raise exceptions.TokenLifetimeError(lifetime=instance.token.seconds_remaining)
        else:
            log.debug("Token lifetime is at least 5 minutes. Continuing...")

        # Proceed with original function
        return await func(*args, **kwargs)

    return wrapper
