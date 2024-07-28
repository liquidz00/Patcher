from datetime import datetime, timezone
from typing import AnyStr, Optional

import keyring
from keyring.errors import PasswordDeleteError
from pydantic import ValidationError

from ..models.jamf_client import JamfClient
from ..models.token import AccessToken
from ..utils import logger


class ConfigManager:
    """Manages configuration settings, mainly loading and saving credentials in keychain"""

    def __init__(self, service_name: AnyStr = "Patcher"):
        """
        Initializes the ConfigManager with a specific service name.

        :param service_name: The name of the service for storing credentials in the keyring.
            Defaults to 'Patcher'.
        :type service_name: AnyStr
        """
        self.log = logger.LogMe(self.__class__.__name__)
        self.service_name = service_name
        self.log.debug(f"Initializing ConfigManager with service name: {service_name}")

    def get_credential(self, key: AnyStr) -> AnyStr:
        """
        Retrieves a specified credential from the keyring.

        :param key: The key of the credential to retrieve.
        :type key: AnyStr
        :return: The retrieved credential value.
        :rtype: AnyStr
        """
        self.log.debug(f"Retrieving credential for key: {key}")
        credential = keyring.get_password(self.service_name, key)
        if credential:
            self.log.info(f"Credential for key '{key}' retrieved successfully")
        else:
            self.log.warning(f"No credential found for key: {key}")
        return credential

    def set_credential(self, key: AnyStr, value: AnyStr):
        """
        Sets a credential in the keyring.

        :param key: The key of the credential to set.
        :type key: AnyStr
        :param value: The value of the credential to set.
        :type value: AnyStr
        """
        self.log.debug(f"Setting credential for key: {key}")
        keyring.set_password(self.service_name, key, value)
        self.log.info(f"Credential for key '{key}' set successfully")

    def delete_credential(self, key: AnyStr) -> bool:
        """
        Deletes a credential in the keyring.

        :param key: The key of the credential to delete.
        :type key: AnyStr
        :return: True if credential was able to be removed, False otherwise.
        :rtype: bool
        """
        self.log.debug(f"Deleting credential for key: {key}")
        try:
            keyring.delete_password(self.service_name, key)
            self.log.info(f"Credential {key} deleted as expected.")
            return True
        except PasswordDeleteError as e:
            self.log.warning(f"Could not delete credential for {key}: {e}")
            return False

    def load_token(self) -> AccessToken:
        """
        Loads the access token from the keyring.

        :return: The access token and token expiration.
        :rtype: AccessToken
        """
        self.log.debug("Loading token from keyring")
        token = self.get_credential("TOKEN") or ""
        expires = (
            self.get_credential("TOKEN_EXPIRATION")
            or datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
        )
        self.log.info("Token and expiration loaded from keyring")
        return AccessToken(token=token, expires=expires)

    def attach_client(self) -> Optional[JamfClient]:
        """
        Attaches a :mod:`patcher.models.jamf_client` object using the stored credentials.

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
            return None

    def create_client(self, client: JamfClient):
        """
        Creates a :mod:`patcher.models.jamf_client` object with necessary attributes. Predominantly used by :mod:`patcher.client.setup` class methods.

        :param client: The ``JamfClient`` object to create.
        :type client: ``JamfClient``
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
