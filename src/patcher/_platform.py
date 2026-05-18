import os
import platform

import keyring
from keyring.backends.null import Keyring as NullKeyring


def _configure_keyring() -> None:
    """
    On non-macOS, install a no-op keyring backend so the import chain
    doesn't blow up when no Secret Service is present (CI runners,
    Linux Servers, Docker containers).

    macOS continues to use the system keychain unchanged. Runtime backend can
    still be overridden via the KEYRING_BACKEND env var, which will take
    precedence over this default.
    """
    if platform.system() == "Darwin":
        return

    # honor override
    if os.environ.get("KEYRING_BACKEND"):
        return

    keyring.set_keyring(NullKeyring())
