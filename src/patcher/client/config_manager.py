from datetime import datetime, timezone
from typing import Optional

import keyring
from pydantic import ValidationError

from ..models.jamf_client import JamfClient
from ..models.token import AccessToken
from ..utils import logger
from ..utils.exceptions import PatcherError


class ConfigManager:
    """
    Manages configuration settings, primarily focused on handling credentials stored in the macOS keychain.

    This class provides methods to securely store, retrieve, and manage sensitive information such as
    API tokens and client credentials. It integrates with the ``keyring`` library to interface with the macOS keychain.
    """

    def __init__(self, service_name: str = "Patcher"):
        """
        Initializes the ConfigManager with a specific service name.

        This service name is used as a namespace for storing and retrieving credentials in the keyring,
        allowing you to organize credentials by the service they pertain to.

        :param service_name: The name of the service for storing credentials in the keyring.
            Defaults to 'Patcher'.
        :type service_name: str
        """
        self.log = logger.LogMe(self.__class__.__name__)
        self.service_name = service_name
        self.log.debug(f"Initializing ConfigManager with service name: {service_name}")

    def get_credential(self, key: str) -> str:
        """
        Retrieves a specified credential from the keyring associated with the given key.

        This method is useful for accessing stored credentials without hardcoding them in scripts.
        It ensures that sensitive data like passwords or API tokens are securely stored and retrieved.

        :param key: The key of the credential to retrieve, typically a descriptive name like 'API_KEY'.
        :type key: str
        :return: The retrieved credential value. If the key does not exist, returns ``None``.
        :rtype: str
        """
        self.log.debug(f"Retrieving credential for key: {key}")
        credential = keyring.get_password(self.service_name, key)
        if not credential:
            self.log.warning(f"No credential found for key: {key}")
        return credential

    def set_credential(self, key: str, value: str) -> None:
        """
        Stores a credential in the keyring under the specified key.

        Method is used to securely store sensitive data such as Jamf URL, API Tokens, usernames
        and passwords.

        :param key: The key under which the credential will be stored. This acts as an identifier for the credential.
        :type key: str
        :param value: The value of the credential to store, such as a password or API token.
        :type value: str
        """
        self.log.debug(f"Setting credential for key: {key}")
        keyring.set_password(self.service_name, key, value)
        self.log.info(f"Credential for key '{key}' set successfully")

    def load_token(self) -> AccessToken:
        """
        Loads the access token and its expiration from the keyring.

        :return: An :class:`~patcher.models.token.AccessToken` object containing the token and its
            expiration date.
        :rtype: AccessToken
        """
        self.log.debug("Loading token from keychain")
        token = self.get_credential("TOKEN") or ""
        expires = (
            self.get_credential("TOKEN_EXPIRATION")
            or datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
        )
        self.log.info("Token and expiration loaded from keychain")
        return AccessToken(token=token, expires=expires)  # type: ignore

    def attach_client(self) -> Optional[JamfClient]:
        """
        Creates and returns a :mod:`patcher.models.jamf_client` object using the stored credentials.
        Allows for an optional custom CA file to be passed, which can be useful for environments
        with custom certificate authorities.

        :return: The ``JamfClient`` object if validation is successful, None otherwise.
        :rtype: Optional[JamfClient]
        """
        self.log.debug("Attaching Jamf client with stored credentials")
        try:
            client = JamfClient(
                client_id=self.get_credential("CLIENT_ID"),
                client_secret=self.get_credential("CLIENT_SECRET"),
                server=self.get_credential("URL"),
                token=self.load_token(),
            )
            self.log.info("Jamf client attached successfully")
            return client
        except ValidationError as e:
            self.log.error(f"Jamf Client failed validation: {e}")
            raise PatcherError(f"Jamf Client failed validation: {e}")

    def create_client(self, client: JamfClient) -> None:
        """
        Stores a `JamfClient` object's credentials in the keyring.

        This method is typically used during the setup process to save the credentials and token of a `JamfClient`
        object into the keyring for secure storage and later use.

        :param client: The `JamfClient` object whose credentials will be stored.
        :type client: JamfClient
        """
        self.log.debug(f"Setting Jamf client: {client.client_id}")
        credentials = {
            "CLIENT_ID": client.client_id,
            "CLIENT_SECRET": client.client_secret,
            "URL": client.server,
            "TOKEN": client.token.token,
            "TOKEN_EXPIRATION": client.token.expires.isoformat(),
        }
        for key, value in credentials.items():
            self.set_credential(key, value)
        self.log.info("Jamf client credentials and token saved successfully")
