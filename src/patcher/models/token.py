from datetime import datetime, timedelta, timezone

from pydantic import Field

from . import Model


class AccessToken(Model):
    """
    Represents a `Bearer Token <https://developer.jamf.com/jamf-pro/docs/jamf-pro-api-overview#bearer-tokens>`_ used for authentication.

    The ``AccessToken`` class additionally provides methods to check the token's expiration
    status and the time remaining before it expires.

    :param token: The access token string used for authentication.
    :type token: :py:class:`str`
    :param expires: The expiration datetime of the token. The default is set to January 1, 1970.
    :type expires: :py:obj:`~datetime.datetime`
    """

    token: str = ""
    expires: datetime = Field(default_factory=lambda: datetime(1970, 1, 1, tzinfo=timezone.utc))

    def __str__(self):
        """
        Returns the string representation of the access token.

        :return: The access token string.
        :rtype: :py:class:`str`
        """
        return self.token

    @property
    def is_expired(self) -> bool:
        """
        This property evaluates whether the access token has expired. A token is
        considered expired if the current time is within 60 seconds of the expiration
        time.

        :return: ``True`` if the token is expired.
        :rtype: :py:class:`bool`
        """
        return self.expires - timedelta(seconds=60) < datetime.now(timezone.utc)

    @property
    def seconds_remaining(self) -> int:
        """
        This property calculates the time remaining before the token expires.
        If the token is already expired, it returns 0.

        :return: The number of seconds remaining until the token expires.
        :rtype: :py:class:`int`
        """
        return max(0, int((self.expires - datetime.now(timezone.utc)).total_seconds()))
