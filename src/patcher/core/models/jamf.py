from urllib.parse import urlparse, urlunparse

from pydantic import Field, SecretStr, field_validator

from ..exceptions import PatcherError
from . import Model


class JamfCredentials(Model):
    """
    Pydantic model carrying the credentials needed to authenticate against
    a Jamf Pro instance: client ID, client secret, and server URL.

    Constructed by :class:`~patcher.clients.token_manager.TokenManager.attach_client`
    from values held in a :class:`~patcher.core.config_manager.ConfigManager` and
    handed to :class:`~patcher.clients.jamf.JamfClient` (the API client) at
    instantiation time.

    ``client_secret`` is held as :class:`pydantic.SecretStr` so accidental
    serialization (``repr``, ``model_dump``, traceback frames, etc.) renders
    the masked placeholder rather than the actual secret. Call
    ``credentials.client_secret.get_secret_value()`` when the plaintext is
    needed (e.g. building the OAuth token request body).

    :ivar client_id: The client ID used for authentication with the Jamf API.
    :type client_id: str
    :ivar client_secret: The client secret used for authentication with the Jamf API.
    :type client_secret: :class:`pydantic.SecretStr`
    :ivar server: The server URL for the Jamf instance.
    :type server: str
    """

    client_id: str
    client_secret: SecretStr
    server: str

    @property
    def base_url(self):
        """
        Gets the base URL of the Jamf server.

        :return: The base URL of the Jamf server.
        :rtype: str
        """
        return self.server

    @staticmethod
    def valid_url(url: str) -> str:
        """
        Validates and formats a URL to ensure it has the correct scheme and structure.

        The scheme is forced to ``https`` regardless of what the caller passed; the
        Jamf Pro API does not accept plain HTTP and silently upgrading prevents
        bearer tokens from ever being shipped over an unencrypted connection by
        a user who typed ``http://`` out of habit.

        :param url: The URL to validate and format.
        :type url: str
        :return: The validated and formatted URL, always ``https://...``.
        :rtype: str
        """
        parsed_url = urlparse(url=url)
        netloc = parsed_url.netloc if parsed_url.netloc else parsed_url.path.split("/")[0]
        path = (
            "/" + "/".join(parsed_url.path.split("/")[1:])
            if len(parsed_url.path.split("/")) > 1
            else ""
        )
        new_url = urlunparse(("https", netloc, path.rstrip("/"), "", "", ""))
        return new_url.rstrip("/")

    @field_validator("client_id", "client_secret", mode="before")
    def not_empty(cls, value):
        """
        Ensures that the `client_id` and `client_secret` fields are not empty, raising
        a ``PatcherError`` if they are.

        :param value: The value to validate.
        :type value: str
        :return: The validated value.
        :rtype: str
        :raises PatcherError: If the value is empty.
        """
        if not value:
            # Avoid echoing the field value back; some Pydantic error paths
            # surface this PatcherError message and logging the empty value
            # itself is fine, but the validator runs before SecretStr wrap
            # so an attacker who triggers this on a non-empty-but-invalid
            # value would otherwise see it in the message.
            raise PatcherError("Field cannot be empty")
        return value

    @field_validator("server", mode="before")
    def validate_url(cls, v):
        """
        Validates that the `~patcher.core.models.jamf.JamfCredentials.server` field contains a valid and properly
        formatted URL by calling the `~patcher.core.models.jamf.JamfCredentials.valid_url` method.

        :param v: The server URL to validate.
        :type v: str
        :return: The validated and formatted server URL.
        :rtype: str
        """
        return cls.valid_url(v)


class ApiRoleModel(Model):
    """
    Represents an API role with specific privileges required for Patcher to operate.

    :ivar display_name: The name of the API role.
    :type display_name: str
    :ivar privileges: A list of privileges assigned to the API role. These privileges
                      determine the actions that the role can perform.
    :type privileges: list[str]
    """

    display_name: str = "Patcher-Role"
    privileges: list[str] = Field(
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
    Configuration for a Jamf Pro API client (auth scopes, display name,
    enabled flag, token lifetime). Constructed during ``patcherctl --setup``
    when Patcher creates the API client on the Jamf side via the Standard
    setup flow.

    :ivar auth_scopes: A list of authentication scopes assigned to the API client. These
                       scopes define the level of access the client has.
    :type auth_scopes: list[str]
    :ivar display_name: The name of the API client.
    :type display_name: str
    :ivar enabled: Indicates whether the API client is currently enabled or disabled.
    :type enabled: bool
    :ivar token_lifetime: The lifetime of the access token in seconds. This value
                          determines how long the token remains valid.
    :type token_lifetime: int
    """

    auth_scopes: list[str] = Field(default_factory=lambda: ["Patcher-Role"])
    display_name: str = "Patcher-Client"
    enabled: bool = True
    token_lifetime: int = 1800
