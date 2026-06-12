"""Credential resolution: keychain-backed or in-memory."""

import re

import keyring
from keyring.errors import KeyringError

from .exceptions import CredentialError
from .logger import LogMe
from .models.jamf import JamfCredentials
from .models.token import AccessToken

# macOS Security framework -25244 / errSecInvalidOwnerEdit fires when a
# different process identity tries to update a Keychain item. See issue #68.
_OWNER_EDIT_ERROR_PATTERN = re.compile(r"-25244|errSecInvalidOwnerEdit", re.IGNORECASE)


def _is_owner_edit_error(exc: Exception) -> bool:
    """True if ``exc`` is the macOS Keychain ``-25244`` ACL-block error."""
    return bool(_OWNER_EDIT_ERROR_PATTERN.search(str(exc)))


class ConfigManager:
    """Resolves Jamf credentials from the macOS keychain, or holds them in memory for library use."""

    def __init__(
        self,
        service_name: str = "Patcher",
        in_memory_credentials: dict[str, str] | None = None,
    ):
        """
        Manages configuration settings, primarily focused on handling credentials stored in the macOS keychain.

        This class provides methods to securely store, retrieve, and manage sensitive information such as
        API tokens and client credentials. It integrates with the ``keyring`` library to interface with the macOS keychain.

        ``ConfigManager`` objects are initialized with a default service name of "Patcher", which is used as a
        namespace for storing and retrieving credentials in macOS keychain.

        For non-interactive use (CI/CD environments without a keychain backend), pass
        ``in_memory_credentials`` to bypass the keychain entirely. Reads check the
        in-memory dict first and fall through to keyring only if the key is absent.
        Writes go to the in-memory dict only; keyring is not touched.

        :param service_name: Service name for storing credentials in the keyring. Defaults to 'Patcher'.
        :type service_name: str
        :param in_memory_credentials: Optional dict of credentials held in memory; when present
            the keyring is not used for either reads or writes.
        :type in_memory_credentials: dict[str, str] | None
        """
        self.log = LogMe(self.__class__.__name__)
        self.service_name = service_name
        self._memory: dict[str, str] | None = (
            dict(in_memory_credentials) if in_memory_credentials is not None else None
        )
        mode = "in-memory" if self._memory is not None else "keyring"
        self.log.debug(f"ConfigManager initialized with service name: {self.service_name} ({mode})")

    @property
    def in_memory_mode(self) -> bool:
        """Whether this manager bypasses the keyring (CI/CD-friendly mode)."""
        return self._memory is not None

    def get_credential(self, key: str) -> str:
        """
        Retrieves a credential by key. In in-memory mode, returns from the
        in-memory dict (or ``None`` if absent). Otherwise reads from the
        macOS keychain.

        :param key: The key of the credential to retrieve, typically a descriptive name like 'API_KEY'.
        :type key: str
        :return: The retrieved credential value.
        :rtype: str
        :raises CredentialError: If the specified credential could not be retrieved.
        """
        self.log.debug(f"Attempting to retrieve credential for key: '{key}'")

        if self.in_memory_mode:
            credential = self._memory.get(key)
            if credential:
                self.log.info(f"Credential for key '{key}' retrieved from in-memory store.")
            else:
                self.log.warning(f"Credential for key '{key}' not present in in-memory store.")
            return credential

        try:
            credential = keyring.get_password(self.service_name, key)
            if credential:
                self.log.info(f"Credential for key '{key}' retrieved successfully.")
            else:
                self.log.warning(f"Credential for key '{key}' is missing or empty.")
            return credential
        except KeyringError as e:
            raise CredentialError(
                "Unable to retrieve credential as expected",
                key=key,
                error_msg=str(e),
            )

    def set_credential(self, key: str, value: str) -> None:
        """
        Stores a credential. In in-memory mode, writes to the in-memory dict
        only; the keychain is never touched. Otherwise writes to the macOS
        keychain.

        :param key: The key under which the credential will be stored. This acts as an identifier for the credential.
        :type key: str
        :param value: The value of the credential to store, such as a password or API token.
        :type value: str
        :raises CredentialError: If the specified credential could not be saved.
        """
        self.log.debug(f"Attempting to store credential for key: '{key}'")

        if self.in_memory_mode:
            self._memory[key] = value
            self.log.info(f"Credential for key '{key}' stored in in-memory store.")
            return

        try:
            keyring.set_password(self.service_name, key, value)
            self.log.info(f"Credential for key '{key}' set successfully")
        except KeyringError as e:
            if _is_owner_edit_error(e):
                # ``owner_mismatch=True`` lets the CLI preflight detect this case programmatically.
                raise CredentialError(
                    "Patcher's Keychain entries are bound to a different Python interpreter "
                    "and can't be updated by this one. "
                    "Clear existing entries with `security delete-generic-password -s Patcher` "
                    "and re-run setup with `patcherctl --fresh`.",
                    key=key,
                    owner_mismatch=True,
                    error_msg=str(e),
                ) from e
            raise CredentialError(
                "Unable to save credential as expected", key=key, error_msg=str(e)
            ) from e

    def delete_credential(self, key: str) -> bool:
        """
        Deletes the provided credential under the specified key. Primarily intended for
        use with the ``--reset`` flag (See :meth:`~patcher.core.config_manager.ConfigManager.reset_config`).

        Deletion is best-effort and always reports success: an absent credential is
        already in the desired state, and a present-but-undeletable one is overwritten
        at the next setup. A genuinely broken keyring fails loudly at write time in
        :meth:`set_credential`, which is the right place to surface it.

        :param key: The credential to delete.
        :type key: str
        :return: Always True (best-effort; see above).
        :rtype: bool
        """
        self.log.debug(f"Attempting to delete credential for key: '{key}'")
        if self.in_memory_mode:
            self._memory.pop(key, None)
            self.log.info(f"Credential for key '{key}' removed from in-memory store.")
            return True
        try:
            keyring.delete_password(self.service_name, key)
            self.log.info(f"Credential for key '{key}' deleted successfully.")
        except KeyringError as e:
            # Best-effort: a stale credential is overwritten at next setup; a broken keyring fails at set_credential.
            self.log.warning(
                f"Could not delete credential for '{key}' (overwritten at setup). Details: {e}"
            )
        return True

    def create_client(self, client: JamfCredentials, token: AccessToken) -> None:
        """
        Persist a ``JamfCredentials`` object plus its bearer token into the
        configured credential backend (keyring or in-memory).

        Used during setup once a JamfCredentials has been validated and a
        token has been fetched. Stores ``CLIENT_ID``, ``CLIENT_SECRET``,
        ``URL``, ``TOKEN``, ``TOKEN_EXPIRATION``.

        :param client: The ``JamfCredentials`` object whose values will be stored.
        :type client: :class:`~patcher.core.models.jamf.JamfCredentials`
        :param token: The ``AccessToken`` object to save.
        :type token: :class:`~patcher.core.models.token.AccessToken`
        :raises CredentialError: If any individual credential write fails (propagated from
            :meth:`~patcher.core.config_manager.ConfigManager.set_credential`).
        """
        self.log.debug(f"Storing credentials for client ending in: {(client.client_id[-4:])}")
        credentials = {
            "CLIENT_ID": client.client_id,
            "CLIENT_SECRET": client.client_secret.get_secret_value(),
            "URL": client.base_url,
            "TOKEN": token.token.get_secret_value(),
            "TOKEN_EXPIRATION": str(token.expires),
        }
        for k, v in credentials.items():
            self.set_credential(k, v)

        self.log.info(
            f"Credentials for client ending in '{(client.client_id[-4:])}' stored successfully."
        )

    def reset_config(self) -> bool:
        """
        Resets all credentials by deleting them from the keyring.

        :return: True if all credentials were successfully deleted, False otherwise.
        :rtype: bool
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
