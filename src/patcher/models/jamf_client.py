from typing import List
from urllib.parse import urlparse, urlunparse

from pydantic import Field, field_validator

from ..utils.exceptions import PatcherError
from . import Model


class JamfClient(Model):
    """
    Represents a Jamf client configuration.

    This class is responsible for holding the configuration necessary to interact with the Jamf API,
    including client credentials, server information, and :class:`~patcher.models.token.AccessToken` objects.

    :ivar client_id: The client ID used for authentication with the Jamf API.
    :type client_id: :py:class:`str`
    :ivar client_secret: The client secret used for authentication with the Jamf API.
    :type client_secret: :py:class:`str`
    :ivar server: The server URL for the Jamf API.
    :type server: :py:class:`str`

    .. admonition:: Removed in version 2.0
        :class: danger

        :class:`~patcher.models.token.AccessToken` objects are handled exclusively by the :class:`~patcher.client.token_manager.TokenManager` class. This ensures 'stale' tokens are not used, causing 401 responses.
    """

    client_id: str
    client_secret: str
    server: str

    @property
    def base_url(self):
        """
        Gets the base URL of the Jamf server.

        :return: The base URL of the Jamf server.
        :rtype: :py:class:`str`
        """
        return self.server

    @staticmethod
    def valid_url(url: str) -> str:
        """
        Validates and formats a URL to ensure it has the correct scheme and structure.

        This method checks if the provided URL has a scheme (e.g., 'https') and a
        network location (netloc). If the scheme is missing, 'https' is assumed.
        The method returns the validated and correctly formatted URL.

        :param url: The URL to validate and format.
        :type url: :py:class:`str`
        :return: The validated and formatted URL.
        :rtype: :py:class:`str`
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

    @field_validator("client_id", "client_secret", mode="before")
    def not_empty(cls, value):
        """
        Ensures that the `client_id` and `client_secret` fields are not empty, raising
        a ``PatcherError`` if they are.

        :param value: The value to validate.
        :type value: :py:class:`str`
        :return: The validated value.
        :rtype: :py:class:`str`
        :raises PatcherError: If the value is empty.
        """
        if not value:
            raise PatcherError("Field cannot be empty", field=value)
        return value

    @field_validator("server", mode="before")
    def validate_url(cls, v):
        """
        Validates that the `~patcher.models.jamf_client.JamfClient.server` field contains a valid and properly
        formatted URL by calling the `~patcher.models.jamf_client.JamfClient.valid_url` method.

        :param v: The server URL to validate.
        :type v: :py:class:`str`
        :return: The validated and formatted server URL.
        :rtype: :py:class:`str`
        """
        return cls.valid_url(v)


class ApiRoleModel(Model):
    """
    Represents an API role with specific privileges required for Patcher to operate.

    :ivar display_name: The name of the API role.
    :type display_name: :py:class:`str`
    :ivar privileges: A list of privileges assigned to the API role. These privileges
                      determine the actions that the role can perform.
    :type privileges: :py:obj:`~typing.List` of :py:class:`str`
    """

    display_name: str = "Patcher-Role"
    privileges: List[str] = Field(
        default_factory=lambda: [
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
    )


class ApiClientModel(Model):
    """
    The ``ApiClient`` class defines the configuration for an API client, including its
    authentication scopes, display name, whether it is enabled, and the token lifetime.

    :ivar auth_scopes: A list of authentication scopes assigned to the API client. These
                       scopes define the level of access the client has.
    :type auth_scopes: :py:obj:`~typing.List` of :py:class:`str`
    :ivar display_name: The name of the API client.
    :type display_name: :py:class:`str`
    :ivar enabled: Indicates whether the API client is currently enabled or disabled.
    :type enabled: :py:class:`bool`
    :ivar token_lifetime: The lifetime of the access token in seconds. This value
                          determines how long the token remains valid.
    :type token_lifetime: :py:class:`int`
    """

    auth_scopes: List[str] = Field(default_factory=lambda: ["Patcher-Role"])
    display_name: str = "Patcher-Client"
    enabled: bool = True
    token_lifetime: int = 1800
