from functools import wraps
from typing import Any, Callable

from pydantic import ValidationError

from .exceptions import TokenError


# Automatic checking/refreshing of AccessToken
def check_token(func: Callable) -> Any:
    """
    Decorator that ensures the validity of an :class:`~patcher.models.token.AccessToken` before
    executing a function.

    The ``check_token`` decorator performs several key tasks before the decorated
    function is executed:

    1. It validates the configuration of the token manager's client.
    2. It checks if the current access token is valid. If the token is invalid,
       it attempts to refresh the token.

    This decorator is intended for use with asynchronous methods that require
    a valid and sufficiently long-lived access token to interact with the Jamf API.

    :param func: The asynchronous function to be decorated.
    :type func: :py:obj:`~typing.Callable`
    :return: The result of the decorated function.
    :rtype: :py:obj:`~typing.Any`
    :raises TokenError: If the AccessToken fails validation (is invalid), if refresh fails or returns ``None``.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        instance = args[0]
        token_manager = instance.token_manager
        log = instance.log

        log.debug(f"Validating access token for function {func.__name__}")
        try:
            await token_manager.ensure_valid_token()
            latest_token = token_manager.token
            log.info(f"Token after validation: {latest_token.token[-4:]}")
        except ValidationError as e:
            raise TokenError("AccessToken failed validation", error_msg=str(e))
        except TokenError:
            raise

        # Proceed with original function
        return await func(*args, **kwargs)

    return wrapper
