from typing import List, Optional
from urllib.parse import urlparse, urlunparse

from pydantic import field_validator

from . import Model
from .token import AccessToken


class JamfClient(Model):
    """
    Represents a Jamf client configuration.

    This class is responsible for holding the configuration necessary to interact
    with the Jamf API, including client credentials, server information, and SSL
    settings.

    :param client_id: The client ID used for authentication with the Jamf API.
    :type client_id: str

    :param client_secret: The client secret used for authentication with the Jamf API.
    :type client_secret: str

    :param server: The server URL for the Jamf API.
    :type server: str

    :param token: The access token used for authenticating API requests. Defaults to None.
    :type token: Optional[AccessToken]
    """

    client_id: str
    client_secret: str
    server: str
    token: Optional[AccessToken] = None

    @staticmethod
    def valid_url(url: str) -> str:
        """
        Validates and formats a URL to ensure it has the correct scheme and structure.

        This method checks if the provided URL has a scheme (e.g., 'https') and a
        network location (netloc). If the scheme is missing, 'https' is assumed.
        The method returns the validated and correctly formatted URL.

        :param url: The URL to validate and format.
        :type url: str
        :return: The validated and formatted URL.
        :rtype: str
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
        Validates that fields for client ID and client secret are not empty.

        Ensures that the `client_id` and `client_secret` fields are not empty, raising
        a ``ValueError`` if they are.

        :param value: The value to validate.
        :type value: str
        :raises ValueError: If the value is empty.
        :return: The validated value.
        :rtype: str
        """
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @classmethod
    @field_validator("server", mode="before")
    def validate_url(cls, v):
        """
        Validates and formats the server URL.

        This method ensures that the ``server`` field contains a valid and properly
        formatted URL by calling the ``valid_url`` method.

        :param v: The server URL to validate.
        :type v: str
        :return: The validated and formatted server URL.
        :rtype: str
        """
        return cls.valid_url(v)

    @property
    def base_url(self):
        """
        Gets the base URL of the Jamf server.

        :return: The base URL of the Jamf server.
        :rtype: str
        """
        return self.server

    @property
    def headers(self):
        return {"accept": "application/json", "Authorization": f"Bearer {self.token}"}


class ApiRoleModel(Model):
    """
    Represents an API role with specific privileges required for Patcher to operate.

    The ``ApiRole`` class encapsulates the role's name and the list of privileges
    associated with that role. This is necessary for managing access control and
    permissions within the Jamf API.

    :ivar display_name: The name of the API role.
    :type display_name: str
    :ivar privileges: A list of privileges assigned to the API role. These privileges
                      determine the actions that the role can perform.
    :type privileges: List[str]
    """

    display_name: str = "Patcher-Role"
    privileges: List[str] = [
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


class ApiClientModel(Model):
    """
    Represents an API client with specific authentication scopes and settings required for Patcher.

    The ``ApiClient`` class defines the configuration for an API client, including its
    authentication scopes, display name, whether it is enabled, and the token lifetime.

    :ivar auth_scopes: A list of authentication scopes assigned to the API client. These
                       scopes define the level of access the client has.
    :type auth_scopes: List[str]
    :ivar display_name: The name of the API client.
    :type display_name: str
    :ivar enabled: Indicates whether the API client is currently enabled or disabled.
    :type enabled: bool
    :ivar token_lifetime: The lifetime of the access token in seconds. This value
                          determines how long the token remains valid.
    :type token_lifetime: int
    """

    auth_scopes: List[str] = ["Patcher-Role"]
    display_name: str = "Patcher-Client"
    enabled: bool = True
    token_lifetime: int = 1800
