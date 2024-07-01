from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, field_validator, Field
from urllib.parse import urlparse, urlunparse
from typing import Optional, AnyStr
from src.Patcher import logger

logthis = logger.setup_child_logger("models", __name__)


class AccessToken(BaseModel):
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


class JamfClient(BaseModel):
    """
    Represents a Jamf client configuration.

    :param client_id: The client ID for the Jamf client.
    :type client_id: AnyStr
    :param client_secret: The client secret for the Jamf client.
    :type client_secret: AnyStr
    :param server: The server URL for the Jamf client.
    :type server: AnyStr
    :param token: The access token for the Jamf client.
    :type token: Optional[AccessToken]
    :param max_concurrency: The maximum concurrency level for API calls.
        Defaults to 5 per Jamf Developer documentation.
    :type max_concurrency: int
    """

    client_id: AnyStr
    client_secret: AnyStr
    server: AnyStr
    token: Optional[AccessToken] = None
    max_concurrency: int = 5

    @staticmethod
    def valid_url(url: AnyStr) -> AnyStr:
        """
        Validates and formats a URL to ensure it has the correct scheme and structure.

        :param url: The URL to validate.
        :type url: AnyStr
        :return: The validated and formatted URL.
        :rtype: AnyStr
        """
        parsed_url = urlparse(url=url)
        scheme = "https" if not parsed_url.scheme else parsed_url.scheme
        netloc = (
            parsed_url.netloc if parsed_url.netloc else parsed_url.path.split("/")[0]
        )
        path = (
            "/" + "/".join(parsed_url.path.split("/")[1:])
            if len(parsed_url.path.split("/")) > 1
            else ""
        )
        new_url = urlunparse((scheme, netloc, path.rstrip("/"), "", "", ""))
        return new_url.rstrip("/")

    @field_validator("client_id", "client_secret", mode="before")
    def not_empty(cls, value):
        """
        Validates that the field is not empty.

        :param value: The value to validate.
        :type value: AnyStr
        :raises ValueError: If the value is empty.
        :return: The validated value.
        :rtype: AnyStr
        """
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @field_validator("server", mode="before")
    def validate_url(cls, v):
        """
        Validates and formats the server URL.

        :param v: The server URL to validate.
        :type v: AnyStr
        :return: The validated and formatted server URL.
        :rtype: AnyStr
        """
        return cls.valid_url(v)

    @property
    def base_url(self):
        """
        Gets the base URL of the server.

        :return: The base URL of the server.
        :rtype: AnyStr
        """
        return self.server

    def set_max_concurrency(self, concurrency: int):
        """
        Sets the maximum concurrency level for API calls. It is **strongly
            recommended** to limit API call concurrency to no more than 5 connections.
            See https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices

        :param concurrency: The new maximum concurrency level.
        :type concurrency: int
        """
        if concurrency < 1:
            logthis.error("Concurrency level must be at least 1!")
            raise ValueError("Concurrency level must be at least 1. ")
        self.max_concurrency = concurrency
