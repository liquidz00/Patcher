import keyring
from keyring.errors import KeyringError
from pydantic import ValidationError

from ..models.jamf_client import JamfClient
from ..models.token import AccessToken
from ..utils.exceptions import CredentialError, PatcherError
from ..utils.logger import LogMe


class ConfigManager:
    def __init__(self, service_name: str = "Patcher"):
        """
        Manages configuration settings, primarily focused on handling credentials stored in the macOS keychain.

        This class provides methods to securely store, retrieve, and manage sensitive information such as
        API tokens and client credentials. It integrates with the ``keyring`` library to interface with the macOS keychain.

        ``ConfigManager`` objects are initialized with a default service name of "Patcher", which is used as a
        namespace for storing and retrieving credentials in macOS keychain.

        :param service_name: Service name for storing credentials in the keyring. Defaults to 'Patcher'.
        :type service_name: :py:class:`str`
        """
        self.log = LogMe(self.__class__.__name__)
        self.service_name = service_name
        self.log.debug(f"ConfigManager initialized with service name: {self.service_name}")

    def get_credential(self, key: str) -> str:
        """
        This method is useful for accessing stored credentials without hardcoding them in scripts.
        It ensures that sensitive data like passwords or API tokens are securely stored and retrieved.

        :param key: The key of the credential to retrieve, typically a descriptive name like 'API_KEY'.
        :type key: :py:class:`str`
        :return: The retrieved credential value.
        :rtype: :py:class:`str`
        :raises CredentialError: If the specified credential could not be retrieved.
        """
        self.log.debug(f"Attempting to retrieve credential for key: '{key}'")
        try:
            credential = keyring.get_password(self.service_name, key)
            if credential:
                self.log.info(f"Credential for key '{key}' retrieved successfully.")
            else:
                self.log.warning(f"Credential for key '{key}' is missing or empty.")
            return credential
        except KeyringError as e:
            self.log.error(f"Unable to retrieve credential for '{key}'. Details: {e}")
            raise CredentialError(
                "Unable to retrieve credential as expected",
                key=key,
                error_msg=str(e),
            )

    def set_credential(self, key: str, value: str) -> None:
        """
        Stores a credential in the keyring under the specified key.

        Method is used to securely store sensitive data such as Jamf URL, API Tokens, and API credentials
        such as client ID and client secret.

        :param key: The key under which the credential will be stored. This acts as an identifier for the credential.
        :type key: :py:class:`str`
        :param value: The value of the credential to store, such as a password or API token.
        :type value: :py:class:`str`
        :raises CredentialError: If the specified credential could not be saved.
        """
        self.log.debug(f"Attempting to store credential for key: '{key}'")
        try:
            keyring.set_password(self.service_name, key, value)
            self.log.info(f"Credential for key '{key}' set successfully")
        except KeyringError as e:
            self.log.error(f"Unable to save credential for '{key}'. Details: {e}")
            raise CredentialError(
                "Unable to save credential as expected", key=key, error_msg=str(e)
            )

    def delete_credential(self, key: str) -> bool:
        """
        Deletes the provided credential in the keyring under the specified key. Primarily intended for
        use with the ``--reset`` flag (See :meth:`~patcher.client.config_manager.ConfigManager.reset`).

        If the specified credential could not be deleted, an error is logged.

        :param key: The credential to delete.
        :type key: :py:class:`str`
        :return: True if the credential was successfully deleted, False otherwise.
        :rtype: :py:class:`bool`
        """
        self.log.debug(f"Attempting to delete credential for key: '{key}'")
        try:
            keyring.delete_password(self.service_name, key)
            self.log.info(f"Credential for key '{key}' deleted successfully.")
            return True
        except KeyringError as e:
            self.log.warning(f"Failed to delete credential for '{key}'. Details: {e}")
            return False

    def load_token(self) -> AccessToken:
        """
        Loads the ``AccessToken`` and its expiration from the keyring.

        If either the AccessToken string or AccessToken expiration cannot
        be retrieved, a :exc:`~patcher.utils.exceptions.CredentialError` is raised.

        :return: An AccessToken object containing the token and its expiration date.
        :rtype: :class:`~patcher.models.token.AccessToken`
        """
        self.log.debug("Attempting to load token and expiration from keychain.")
        try:
            token = self.get_credential("TOKEN")
            expires = self.get_credential("TOKEN_EXPIRATION")
            self.log.info("Token and expiration loaded from keychain")
            return AccessToken(token=token, expires=expires)  # type: ignore
        except CredentialError:
            self.log.warning("Token or expiration is missing, loading failed.")
            raise

    def attach_client(self) -> JamfClient:
        """
        Creates and returns a ``JamfClient`` object using the stored credentials.

        :return: The ``JamfClient`` object if validation is successful.
        :rtype: :class:`~patcher.models.jamf_client.JamfClient`
        :raises PatcherError: If ``JamfClient`` object fails pydantic validation.
        """
        self.log.debug("Attempting to attach JamfClient with stored credentials")
        try:
            client = JamfClient(
                client_id=self.get_credential("CLIENT_ID"),
                client_secret=self.get_credential("CLIENT_SECRET"),
                server=self.get_credential("URL"),
                token=self.load_token(),
            )
            self.log.info(f"JamfClient ending in ({(client.client_id[-4:])}) attached successfully")
            return client
        except ValidationError as e:
            self.log.error(f"Failed attaching JamfClient due to validation error. Details: {e}")
            raise PatcherError(
                "Unable to attach JamfClient due to invalid configuration",
                error_msg=str(e),
            )

    def create_client(self, client: JamfClient) -> None:
        """
        Stores a ``JamfClient`` object's credentials in the keyring.

        This method is typically used during the setup process to save the credentials and token of a ``JamfClient``
        object into the keyring for secure storage and later use.

        If any of the client credentials could not be saved, a :exc:`~patcher.utils.exceptions.CredentialError`
        is raised via the :meth:`~patcher.client.config_manager.ConfigManager.set_credential` method.

        :param client: The ``JamfClient`` object whose credentials will be stored.
        :type client: :class:`~patcher.models.jamf_client.JamfClient`
        """
        self.log.debug(f"Storing credentials for JamfClient ending in: {(client.client_id[-4:])}")
        credentials = {
            "CLIENT_ID": client.client_id,
            "CLIENT_SECRET": client.client_secret,
            "URL": client.server,
            "TOKEN": client.token.token,
            "TOKEN_EXPIRATION": client.token.expires.isoformat(),
        }
        for k, v in credentials.items():
            self.set_credential(k, v)

        self.log.info(
            f"Credentials for JamfClient ending in '{(client.client_id[-4:])}' stored successfully."
        )

    def reset(self) -> bool:
        """
        Resets all credentials by deleting them from the keyring.

        :return: True if all credentials were successfully deleted, False otherwise.
        :rtype: :py:class:`bool`
        """
        self.log.debug("Attempting to reset all stored credentials.")
        creds = ["CLIENT_ID", "CLIENT_SECRET", "URL", "TOKEN", "TOKEN_EXPIRATION"]
        results = [self.delete_credential(cred) for cred in creds]
        all_deleted = all(results)
        if all_deleted:
            self.log.info("All credentials reset successfully.")
        else:
            self.log.warning("Not all credentials could be deleted.")
        return all_deleted
