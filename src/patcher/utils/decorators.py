from functools import wraps
from typing import Any, Callable

from pydantic import ValidationError

from ..utils import exceptions


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
        log = instance.log

        try:
            log.info("Validating access token before API call...")
            await token_manager.ensure_valid_token()
        except ValidationError as e:
            log.error(f"Failed validation: {e}")
            raise
        except exceptions.TokenFetchError as e:
            log.error(f"Failed to refresh token: {e}")
            raise
        except exceptions.TokenLifetimeError as e:
            log.error(f"Token lifetime insufficient: {e}")
            raise

        # Proceed with original function
        return await func(*args, **kwargs)

    return wrapper
