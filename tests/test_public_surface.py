"""Smoke tests for the public ``patcher`` package surface.

Verifies that the symbols exposed in ``patcher/__init__.py`` resolve to
their canonical implementations, that internal classes stay internal, and
that ``__all__`` accurately describes the public API.
"""

from src.patcher.client.jamf import JamfClient as _JamfFromClient
from src.patcher.core.exceptions import APIResponseError as _APIErr
from src.patcher.core.exceptions import PatcherError as _PatcherErr
from src.patcher.core.installomator import InstallomatorClient as _IomCanonical
from src.patcher.core.models.patch import PatchDevice as _DeviceFromCore
from src.patcher.core.models.patch import PatchTitle as _TitleFromCore


def test_facade_exposes_jamf_client():
    from src.patcher import JamfClient

    assert JamfClient is _JamfFromClient


def test_facade_exposes_installomator_client():
    """InstallomatorClient is the public name for the Installomator label-matching service."""
    from src.patcher import InstallomatorClient

    assert InstallomatorClient is _IomCanonical


def test_facade_exposes_return_shapes():
    from src.patcher import PatchDevice, PatchTitle

    assert PatchTitle is _TitleFromCore
    assert PatchDevice is _DeviceFromCore


def test_facade_exposes_exceptions():
    from src.patcher import APIResponseError, PatcherError

    assert APIResponseError is _APIErr
    assert PatcherError is _PatcherErr


def test_facade_hides_cli_only_surface():
    """Setup, SetupType, UIConfigManager, Animation must not leak through the facade."""
    import src.patcher as patcher

    for name in ("Setup", "SetupType", "SetupError", "UIConfigManager", "Animation"):
        assert not hasattr(patcher, name), f"`{name}` should be CLI-only, not on the public facade"


def test_facade_hides_internal_models():
    """JamfCredentials, AccessToken, Label are internal data shapes — not on the facade."""
    import src.patcher as patcher

    for name in ("JamfCredentials", "AccessToken", "Label"):
        assert not hasattr(patcher, name), (
            f"`{name}` is an internal data shape; library callers should not need it"
        )


def test_facade_hides_advanced_classes():
    """HTTPClient, ConfigManager, DataManager remain importable via submodules but not at root."""
    import src.patcher as patcher

    for name in ("HTTPClient", "ConfigManager", "DataManager"):
        assert not hasattr(patcher, name), (
            f"`{name}` is advanced surface; not part of the headline public facade"
        )


def test_facade_all_matches_exports():
    """Every name in __all__ should resolve as a real attribute on the package."""
    import src.patcher as patcher

    for name in patcher.__all__:
        assert hasattr(patcher, name), f"__all__ promises `{name}` but it is not on the package"
