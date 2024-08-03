from typing import AnyStr, List, Optional
from urllib.parse import urlparse, urlunparse

from pydantic import field_validator

from . import Model
from .token import AccessToken


class JamfClient(Model):
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
    :param max_concurrency: The maximum concurrency level for API calls. Defaults to 5 per Jamf Developer documentation.
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
        netloc = parsed_url.netloc if parsed_url.netloc else parsed_url.path.split("/")[0]
        path = (
            "/" + "/".join(parsed_url.path.split("/")[1:])
            if len(parsed_url.path.split("/")) > 1
            else ""
        )
        new_url = urlunparse((scheme, netloc, path.rstrip("/"), "", "", ""))
        return new_url.rstrip("/")

    @classmethod
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

    @classmethod
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
        Sets the maximum concurrency level for API calls.

        .. warning::
            Changing this value could lead to your Jamf server being unable to perform other basic tasks. See the :ref:`Concurrency <concurrency>` option in the usage documentation.

        It is **strongly recommended** to limit API call concurrency to no more than 5 connections.
        See `Jamf Developer Guide <https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices>`_ for more information.

        :param concurrency: The new maximum concurrency level.
        :type concurrency: int
        """
        if concurrency < 1:
            raise ValueError("Concurrency level must be at least 1. ")
        self.max_concurrency = concurrency


class ApiRole(Model):
    """
    Represents an API role with specific privileges required for Patcher to operate.

    :ivar display_name: The name of the API role.
    :type display_name: AnyStr
    :ivar privileges: A list of privileges assigned ot the API role.
    :type privileges: List[AnyStr]
    """

    display_name: AnyStr = "Patcher-Role"
    privileges: List[AnyStr] = [
        "Read Patch Management Software Titles",
        "Read Patch Policies",
        "Read Mobile Devices",
        "Read Mobile Device Inventory Collection",
        "Read Mobile Device Applications",
        "Read Patch Management Settings",
        "Create API Integrations",
        "Create API Roles",
        "Read API Integrations",
        "Read API Roles",
        "Update API Integrations",
        "Update API Roles",
    ]


class ApiClient(Model):
    """
    Represents an API client with specific authentication scopes and settings required for Patcher.

    :ivar auth_scopes: A list of authentication scopes assigned to the API client.
    :type auth_scopes: List[AnyStr]
    :ivar display_name: The name of the API client.
    :type display_name: AnyStr
    :ivar enabled: Indicates whether the API client is enabled.
    :type enabled: bool
    :ivar token_lifetime: The lifetime of the token in seconds.
    :type token_lifetime: int
    """

    auth_scopes: List[AnyStr] = ["Patcher-Role"]
    display_name: AnyStr = "Patcher-Client"
    enabled: bool = True
    token_lifetime: int = 1800
