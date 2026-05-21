import os

import pytest
from keyring.backends.null import Keyring as NullKeyring


@pytest.fixture
def configure():
    # re-import fresh so import-time side effects are reset
    from patcher._platform import _configure_keyring

    return _configure_keyring


def test_darwin_does_not_touch(mocker, configure):
    """macOS: system keychain always available."""
    mocker.patch("platform.system", return_value="Darwin")
    set_keyring = mocker.patch("patcher._platform.keyring.set_keyring")

    configure()

    set_keyring.assert_not_called()


def test_linux_installs_null_unset(mocker, configure):
    """Linux with no keyring env var should install null backend."""
    mocker.patch("platform.system", return_value="Linux")
    mocker.patch.dict(os.environ, {}, clear=True)
    set_keyring = mocker.patch("patcher._platform.keyring.set_keyring")

    configure()

    set_keyring.assert_called_once()
    installed = set_keyring.call_args.args[0]
    assert isinstance(installed, NullKeyring)


def test_env_precendence(mocker, configure):
    """Linux with env var set should not touch backend."""
    mocker.patch("platform.system", return_value="Linux")
    mocker.patch.dict(os.environ, {"KEYRING_BACKEND": "some.custom.Backend"}, clear=True)
    set_keyring = mocker.patch("patcher._platform.keyring.set_keyring")

    configure()

    set_keyring.assert_not_called()


def test_windows_as_linux(mocker, configure):
    """Anything not Darwin gets null-backend treatment."""
    mocker.patch("platform.system", return_value="Windows")
    mocker.patch.dict(os.environ, {}, clear=True)
    set_keyring = mocker.patch("patcher._platform.keyring.set_keyring")

    configure()

    set_keyring.assert_called_once()
