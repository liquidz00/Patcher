from datetime import datetime, timedelta, timezone
from typing import AnyStr

from pydantic import Field

from .. import logger
from . import Model

logthis = logger.setup_child_logger("AccessToken", __name__)


class AccessToken(Model):
    """
    Represents an access token for authentication.

    :param token: The access token string.
    :type token: AnyStr
    :param expires: the Expiration datetime of the token.
    :type expires: datetime
    """

    token: AnyStr = ""
    expires: datetime = Field(
        default_factory=lambda: datetime(1970, 1, 1, tzinfo=timezone.utc)
    )

    def __str__(self):
        """
        Returns the string representation of the access token.

        :return: The access token string.
        :rtype: str
        """
        return self.token

    @property
    def is_expired(self) -> bool:
        """
        Checks if the access token is expired.

        :return: True if the token is expired, False otherwise.
        :rtype: bool
        """
        return self.expires - timedelta(seconds=60) < datetime.now(timezone.utc)

    @property
    def seconds_remaining(self) -> int:
        """
        Gets the number of seconds remaining until the token expires.

        :return: The number of seconds remaining.
        :rtype: int
        """
        return max(0, int((self.expires - datetime.now(timezone.utc)).total_seconds()))
