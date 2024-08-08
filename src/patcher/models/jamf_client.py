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
    :param ssl_path: The SSL paths for verification. ``aiohttp`` and ``urllib`` both use Python's ``ssl`` library for SSL verification. For environments with security software, SSL verification errors can be thrown and intermediate certificates appended.
    :type ssl_path: ssl.DefaultVerifyPaths
    :param custom_ca_file: Path to a custom CA file that can be appended to default SSL certificate paths.
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

    @classmethod
    @field_validator("ssl_path", mode="before")
    def validate_ssl_paths(cls, v):
        """
        Validates the cafile property of the ``ssl_path`` is not None.

        :param v: The ssl_path value to validate (defaults to ``cafile``)
        :type v: ssl.DefaultVerifyPaths
        :raises ssl.SSLCertVerificationError: If the cafile property is None.
        :return: the validated ssl_path.
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
        Validates the custom CA file path to ensure it is a string.

        :param v: The custom CA file path value to validate.
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
        Gets the base URL of the server.

        :return: The base URL of the server.
        :rtype: AnyStr
        """
        return self.server

    @property
    def cafile(self) -> str:
        """
        Gets the path to the CA file used for SSL verification. If a custom CA file is provided, it is used.

        :return: The path to the CA file.
        :rtype: str
        """
        if self.custom_ca_file:
            return self.custom_ca_file
        return self.ssl_path.cafile

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
