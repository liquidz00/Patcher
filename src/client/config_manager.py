import keyring
from src.model.models import AccessToken, JamfClient
from datetime import datetime, timezone
from src import logger
from pydantic import ValidationError
from typing import Optional, AnyStr

logthis = logger.setup_child_logger("ConfigManager", __name__)


class ConfigManager:
    """Manages configuration settings, mainly loading and saving credentials in keychain"""

    def __init__(self, service_name: AnyStr = "patcher"):
        """
        Initializes the ConfigManager with a specific service name.

        :param service_name: The name of the service for storing credentials in the keyring.
            Defaults to 'patcher'.
        :type service_name: AnyStr
        """
        self.service_name = service_name

    def get_credential(self, key: AnyStr) -> AnyStr:
        """
        Retrieves a specified credential from the keyring.

        :param key: The key of the credential to retrieve.
        :type key: AnyStr
        :return: The retrieved credential value.
        :rtype: AnyStr
        """
        return keyring.get_password(self.service_name, key)

    def set_credential(self, key: AnyStr, value: AnyStr):
        """
        Sets a credential in the keyring.

        :param key: The key of the credential to set.
        :type key: AnyStr
        :param value: The value of the credential to set.
        :type value: AnyStr
        """
        keyring.set_password(self.service_name, key, value)

    def load_token(self) -> AccessToken:
        """
        Loads the access token from the keyring.

        :return: The access token with its expiration date.
        :rtype: AccessToken
        """
        token = self.get_credential("TOKEN") or ""
        expires = (
            self.get_credential("TOKEN_EXPIRATION")
            or datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
        )
        return AccessToken(token=token, expires=expires)

    def attach_client(self) -> Optional[JamfClient]:
        """
        Attaches a Jamf client using the stored credentials.

        :return: The Jamf client if validation is successful, None otherwise.
        :rtype: Optional[JamfClient]
        """
        try:
            return JamfClient(
                client_id=self.get_credential("CLIENT_ID"),
                client_secret=self.get_credential("CLIENT_SECRET"),
                server=self.get_credential("URL"),
                token=self.load_token(),
            )
        except ValidationError as e:
            logthis.error(f"Jamf Client failed validation: {e}")
            return None
