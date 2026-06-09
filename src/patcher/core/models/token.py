"""Model for the Jamf Pro OAuth bearer token."""

from datetime import datetime, timedelta, timezone

from pydantic import Field, SecretStr

from . import Model


class AccessToken(Model):
    """
    Represents a `Bearer Token <https://developer.jamf.com/jamf-pro/docs/jamf-pro-api-overview#bearer-tokens>`_ used for authentication.

    The token is held as :class:`pydantic.SecretStr` so accidental ``repr`` /
    ``model_dump`` / ``str()`` / traceback rendering returns the masked
    placeholder rather than the actual bearer. Use
    ``access_token.token.get_secret_value()`` when constructing the
    ``Authorization`` header or persisting to the keychain.

    :param token: The access token used for authentication.
    :type token: :class:`pydantic.SecretStr`
    :param expires: The expiration datetime of the token. The default is set to January 1, 1970.
    :type expires: datetime
    """

    token: SecretStr = SecretStr("")
    expires: datetime = Field(default_factory=lambda: datetime(1970, 1, 1, tzinfo=timezone.utc))

    def __str__(self):
        """
        Return the masked SecretStr representation (``"**********"``).

        Deliberately masked: an accidental ``str(access_token)`` should not
        emit the bearer token. Callers that need the plaintext should call
        ``access_token.token.get_secret_value()``.
        """
        return str(self.token)

    @property
    def is_expired(self) -> bool:
        """
        This property evaluates whether the access token has expired. A token is
        considered expired if the current time is within 60 seconds of the expiration
        time.

        :return: ``True`` if the token is expired.
        :rtype: bool
        """
        return self.expires - timedelta(seconds=60) < datetime.now(timezone.utc)

    @property
    def seconds_remaining(self) -> int:
        """
        This property calculates the time remaining before the token expires.
        If the token is already expired, it returns 0.

        :return: The number of seconds remaining until the token expires.
        :rtype: int
        """
        return max(0, int((self.expires - datetime.now(timezone.utc)).total_seconds()))
