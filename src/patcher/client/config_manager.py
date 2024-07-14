from datetime import datetime, timezone
from typing import AnyStr, Optional

import keyring
from keyring.errors import PasswordDeleteError
from pydantic import ValidationError

from ..models.jamf_client import JamfClient
from ..models.token import AccessToken
from ..utils import logger

logthis = logger.setup_child_logger("ConfigManager", __name__)


class ConfigManager:
    """Manages configuration settings, mainly loading and saving credentials in keychain"""

    def __init__(self, service_name: AnyStr = "Patcher"):
        """
        Initializes the ConfigManager with a specific service name.

        :param service_name: The name of the service for storing credentials in the keyring.
            Defaults to 'patcher'.
        :type service_name: AnyStr
        """
        logthis.debug(f"Initializing ConfigManager with service name: {service_name}")
        self.service_name = service_name

    def get_credential(self, key: AnyStr) -> AnyStr:
        """
        Retrieves a specified credential from the keyring.

        :param key: The key of the credential to retrieve.
        :type key: AnyStr
        :return: The retrieved credential value.
        :rtype: AnyStr
        """
        logthis.debug(f"Retrieving credential for key: {key}")
        credential = keyring.get_password(self.service_name, key)
        if credential:
            logthis.info(f"Credential for key '{key}' retrieved successfully")
        else:
            logthis.warning(f"No credential found for key: {key}")
        return credential

    def set_credential(self, key: AnyStr, value: AnyStr):
        """
        Sets a credential in the keyring.

        :param key: The key of the credential to set.
        :type key: AnyStr
        :param value: The value of the credential to set.
        :type value: AnyStr
        """
        logthis.debug(f"Setting credential for key: {key}")
        keyring.set_password(self.service_name, key, value)
        logthis.info(f"Credential for key '{key}' set successfully")

    def delete_credential(self, key: AnyStr) -> bool:
        """
        Deletes a credential in the keyring.

        :param key: The key of the credential to delete.
        :type key: AnyStr
        :raises keyring.errors.PasswordDeleteError: If credential could not be deleted.
        :return: True if credential was able to be removed, False otherwise.
        :rtype: bool
        """
        logthis.debug(f"Deleting credential for key: {key}")
        try:
            keyring.delete_password(self.service_name, key)
            logthis.info(f"Credential {key} deleted as expected.")
            return True
        except PasswordDeleteError as e:
            logthis.warning(f"Could not delete credential for {key}: {e}")
            return False

    def load_token(self) -> AccessToken:
        """
        Loads the access token from the keyring.

        :return: The access token with its expiration date.
        :rtype: AccessToken
        """
        logthis.debug("Loading token from keyring")
        token = self.get_credential("TOKEN") or ""
        expires = (
            self.get_credential("TOKEN_EXPIRATION")
            or datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
        )
        logthis.info("Token and expiration loaded from keyring")
        return AccessToken(token=token, expires=expires)

    def attach_client(self) -> Optional[JamfClient]:
        """
        Attaches a Jamf client using the stored credentials.

        :return: The Jamf client if validation is successful, None otherwise.
        :rtype: Optional[JamfClient]
        """
        logthis.debug("Attaching Jamf client with stored credentials")
        try:
            client = JamfClient(
                client_id=self.get_credential("CLIENT_ID"),
                client_secret=self.get_credential("CLIENT_SECRET"),
                server=self.get_credential("URL"),
                token=self.load_token(),
            )
            logthis.info("Jamf client attached successfully")
            return client
        except ValidationError as e:
            logthis.error(f"Jamf Client failed validation: {e}")
            return None

    def create_client(self, client: JamfClient):
        logthis.debug(f"Setting Jamf client: {client.client_id}")
        credentials = {
            "CLIENT_ID": client.client_id,
            "CLIENT_SECRET": client.client_secret,
            "URL": client.server,
            "TOKEN": client.token.token,
            "TOKEN_EXPIRATION": client.token.expires.isoformat(),
        }
        for key, value in credentials.items():
            self.set_credential(key, value)
        logthis.info("Jamf client credentials and token saved successfully")
