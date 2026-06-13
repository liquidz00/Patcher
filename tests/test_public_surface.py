"""
Smoke tests for the public ``patcher`` package surface.

Verifies that the symbols exposed in ``patcher/__init__.py`` resolve to
their canonical implementations, that internal classes stay internal, and
that ``__all__`` accurately describes the public API.

Imports the installed ``patcher`` package (the path users get), not the
``src.patcher`` source tree the rest of the suite reaches through, so a
packaging change that drops a module from the wheel surfaces here.
"""

from unittest.mock import AsyncMock

import pytest

from patcher.clients.installomator import InstallomatorClient as _IomCanonical
from patcher.clients.jamf import JamfClient as _JamfFromClient
from patcher.clients.patcher_api import PatcherAPIClient as _PatcherAPIFromClient
from patcher.core.exceptions import APIResponseError as _APIErr
from patcher.core.exceptions import PatcherError as _PatcherErr
from patcher.core.models.patch import PatchDevice as _DeviceFromCore
from patcher.core.models.patch import PatchTitle as _TitleFromCore
from patcher.core.patcher_client import PatcherClient as _PatcherCanonical


def test_package_exposes_patcher_client():
    """PatcherClient is the headline library entry point."""
    from patcher import PatcherClient

    assert PatcherClient is _PatcherCanonical


@pytest.mark.asyncio
async def test_patcher_client_async_context_manager_closes_jamf():
    """
    ``async with PatcherClient(...)`` releases the connection pool on exit.

    Library callers should be able to wrap PatcherClient in ``async with`` to
    guarantee the underlying httpx connection pool is closed when the block
    exits — no manual ``aclose()`` required.
    """
    from patcher import PatcherClient

    patcher = PatcherClient(
        client_id="cid",
        client_secret="csec",
        server="https://example.com",
    )
    patcher.jamf.aclose = AsyncMock()

    async with patcher as ctx:
        assert ctx is patcher

    patcher.jamf.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_patcher_client_aclose_is_idempotent():
    """
    Calling :meth:`PatcherClient.aclose` multiple times is safe — the
    underlying :class:`HTTPClient.aclose` is itself idempotent.
    """
    from patcher import PatcherClient

    patcher = PatcherClient(
        client_id="cid",
        client_secret="csec",
        server="https://example.com",
    )
    patcher.jamf.aclose = AsyncMock()
    await patcher.aclose()
    await patcher.aclose()
    assert patcher.jamf.aclose.await_count == 2


def test_package_exposes_jamf_client():
    from patcher import JamfClient

    assert JamfClient is _JamfFromClient


def test_package_exposes_installomator_client():
    """InstallomatorClient is the public name for the Installomator label-matching service."""
    from patcher import InstallomatorClient

    assert InstallomatorClient is _IomCanonical


def test_package_exposes_patcher_api_client():
    """PatcherAPIClient is the public name for the Patcher API catalog client."""
    from patcher import PatcherAPIClient

    assert PatcherAPIClient is _PatcherAPIFromClient


def test_package_exposes_return_shapes():
    from patcher import PatchDevice, PatchTitle

    assert PatchTitle is _TitleFromCore
    assert PatchDevice is _DeviceFromCore


def test_package_exposes_exceptions():
    from patcher import APIResponseError, PatcherError

    assert APIResponseError is _APIErr
    assert PatcherError is _PatcherErr


def test_package_hides_cli_only_surface():
    """Setup, SetupType, Animation must not leak through the public package."""
    import patcher

    for name in ("Setup", "SetupType", "SetupError", "Animation"):
        assert not hasattr(patcher, name), f"`{name}` should be CLI-only, not on the public package"


def test_package_hides_internal_models():
    """JamfCredentials, AccessToken, Label are internal data shapes — not on the public package."""
    import patcher

    for name in ("JamfCredentials", "AccessToken", "Label"):
        assert not hasattr(patcher, name), (
            f"`{name}` is an internal data shape; library callers should not need it"
        )


def test_package_hides_advanced_classes():
    """HTTPClient, ConfigManager, DataManager remain importable via submodules but not at root."""
    import patcher

    for name in ("HTTPClient", "ConfigManager", "DataManager"):
        assert not hasattr(patcher, name), (
            f"`{name}` is advanced surface; not part of the headline public package"
        )


def test_package_all_matches_exports():
    """Every name in __all__ should resolve as a real attribute on the package."""
    import patcher

    for name in patcher.__all__:
        assert hasattr(patcher, name), f"__all__ promises `{name}` but it is not on the package"
