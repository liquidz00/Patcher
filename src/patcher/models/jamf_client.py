import ssl
from pathlib import Path
from typing import AnyStr, List, Optional, Union
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
    :type client_id: AnyStr

    :param client_secret: The client secret used for authentication with the Jamf API.
    :type client_secret: AnyStr

    :param server: The server URL for the Jamf API.
    :type server: AnyStr

    :param token: The access token used for authenticating API requests. Defaults to None.
    :type token: Optional[AccessToken]

    :param max_concurrency: The maximum number of concurrent API calls allowed. Defaults to 5.
    :type max_concurrency: int

    :param ssl_path: The SSL verification paths used for SSL certificate verification.
    :type ssl_path: ssl.DefaultVerifyPaths

    :param custom_ca_file: Path to a custom Certificate Authority (CA) file for SSL verification.
                           If provided, this file is used in place of the default CA paths.
    :type custom_ca_file: Optional[Union[str, Path]]
    """

    client_id: AnyStr
    client_secret: AnyStr
    server: AnyStr
    token: Optional[AccessToken] = None
    max_concurrency: int = 5
    ssl_path: ssl.DefaultVerifyPaths = ssl.get_default_verify_paths()
    custom_ca_file: Optional[Union[str, Path]] = None

    @staticmethod
    def valid_url(url: AnyStr) -> AnyStr:
        """
        Validates and formats a URL to ensure it has the correct scheme and structure.

        This method checks if the provided URL has a scheme (e.g., 'https') and a
        network location (netloc). If the scheme is missing, 'https' is assumed.
        The method returns the validated and correctly formatted URL.

        :param url: The URL to validate and format.
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
        Validates that fields for client ID and client secret are not empty.

        Ensures that the `client_id` and `client_secret` fields are not empty, raising
        a ``ValueError`` if they are.

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

        This method ensures that the ``server`` field contains a valid and properly
        formatted URL by calling the ``valid_url`` method.

        :param v: The server URL to validate.
        :type v: AnyStr
        :return: The validated and formatted server URL.
        :rtype: AnyStr
        """
        return cls.valid_url(v)

    @classmethod
    @field_validator("ssl_path", mode="before")
    def validate_ssl_paths(cls, v):
        """
        Validates that the ``cafile`` property of the ``ssl_path`` is not ``None``.

        This method ensures that the SSL certificate file is properly configured.
        If the ``cafile`` property is ``None``, an ``SSLCertVerificationError`` is raised.

        :param v: The ``ssl_path`` value to validate.
        :type v: ssl.DefaultVerifyPaths
        :raises ssl.SSLCertVerificationError: If the ``cafile`` property is ``None``.
        :return: The validated ``ssl_path``.
        :rtype: ssl.DefaultVerifyPaths
        """
        if v.cafile is None:
            raise ssl.SSLCertVerificationError(
                "SSL certificate file is missing or not configured properly, verification has failed."
            )
        return v

    @classmethod
    @field_validator("custom_ca_file", mode="before")
    def validate_custom_ca(cls, v):
        """
        Validates the custom CA file path.

        Ensures that the ``custom_ca_file`` path is provided as a string. If a ``Path``
        object is provided, it is converted to a string.

        :param v: The custom CA file path to validate.
        :type v: Union[str, Path]
        :return: The validated custom CA file path as a string.
        :rtype: str
        """
        if isinstance(v, Path):
            return str(v)
        return v

    @property
    def base_url(self):
        """
        Gets the base URL of the Jamf server.

        :return: The base URL of the Jamf server.
        :rtype: AnyStr
        """
        return self.server

    @property
    def cafile(self) -> str:
        """
        Gets the path to the CA file used for SSL verification.

        If a custom CA file is provided, it is returned; otherwise, the default
        CA file path is used.

        :return: The path to the CA file used for SSL verification.
        :rtype: str
        """
        if self.custom_ca_file:
            return self.custom_ca_file
        return self.ssl_path.cafile

    def set_max_concurrency(self, concurrency: int):
        """
        Sets the maximum concurrency level for API calls.

        This method allows you to set the maximum number of concurrent API calls
        that can be made by the Jamf client. It is recommended to limit this value
        to 5 connections to avoid overloading the Jamf server.

        .. warning::
            Changing this value could lead to your Jamf server being unable to perform other basic tasks. See the :ref:`Concurrency <concurrency>` option in the usage documentation.

        It is **strongly recommended** to limit API call concurrency to no more than 5 connections.
        See `Jamf Developer Guide <https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices>`_ for more information.

        :param concurrency: The new maximum concurrency level.
        :type concurrency: int
        :raises ValueError: If the concurrency level is less than 1.
        """
        if concurrency < 1:
            raise ValueError("Concurrency level must be at least 1. ")
        self.max_concurrency = concurrency


class ApiRole(Model):
    """
    Represents an API role with specific privileges required for Patcher to operate.

    The ``ApiRole`` class encapsulates the role's name and the list of privileges
    associated with that role. This is necessary for managing access control and
    permissions within the Jamf API.

    :ivar display_name: The name of the API role.
    :type display_name: AnyStr
    :ivar privileges: A list of privileges assigned to the API role. These privileges
                      determine the actions that the role can perform.
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

    The ``ApiClient`` class defines the configuration for an API client, including its
    authentication scopes, display name, whether it is enabled, and the token lifetime.

    :ivar auth_scopes: A list of authentication scopes assigned to the API client. These
                       scopes define the level of access the client has.
    :type auth_scopes: List[AnyStr]
    :ivar display_name: The name of the API client.
    :type display_name: AnyStr
    :ivar enabled: Indicates whether the API client is currently enabled or disabled.
    :type enabled: bool
    :ivar token_lifetime: The lifetime of the access token in seconds. This value
                          determines how long the token remains valid.
    :type token_lifetime: int
    """

    auth_scopes: List[AnyStr] = ["Patcher-Role"]
    display_name: AnyStr = "Patcher-Client"
    enabled: bool = True
    token_lifetime: int = 1800
