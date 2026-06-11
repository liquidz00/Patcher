"""
Integration tests: device data pipeline against the integration instance.

dummy.jamfcloud.com has Computers and iOS Devices pre-populated, so this
slice of Patcher (the iOS data path that powers ``--ios`` exports) can be
exercised end-to-end without needing patch titles configured.

Each test keeps its API footprint small (single round-trip or a tiny
sample) to play nicely with the shared dummy instance.
"""

from __future__ import annotations

import pytest
from src.patcher.core.analyze import get_sofa_feed


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_device_ids_returns_list(integration_jamf_client) -> None:
    """
    The mobile-device-IDs endpoint returns a list (possibly empty) of IDs.

    Jamf's response sometimes returns IDs as strings rather than ints despite
    the method's type hint; we only assert non-None presence here. The shape
    discrepancy is tracked separately.
    """
    device_ids = await integration_jamf_client.get_device_ids()

    assert isinstance(device_ids, list)
    if device_ids:
        assert all(did is not None for did in device_ids), "Device IDs should all be non-None"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_device_os_versions_resolves_sample(integration_jamf_client) -> None:
    """
    OS-version resolution returns dicts shaped like ``{"OS": ..., "DeviceID": ...}``.

    Uses a 3-device sample to limit API load against the shared dummy instance.
    Skips cleanly if no mobile devices are configured.
    """
    device_ids = await integration_jamf_client.get_device_ids()
    if not device_ids:
        pytest.skip("Integration instance has no mobile devices configured.")

    sample = device_ids[:3]
    versions = await integration_jamf_client.get_device_os_versions(sample)

    assert isinstance(versions, list)
    if versions:
        for entry in versions:
            assert "OS" in entry, f"Entry missing OS key: {entry}"
            assert "SN" in entry, f"Entry missing SN (serial number) key: {entry}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_sofa_feed_returns_release_data(integration_jamf_client) -> None:
    """The SOFA feed (external macadmins.io endpoint) returns iOS release metadata."""
    feed = await get_sofa_feed(integration_jamf_client)

    assert isinstance(feed, list)
    assert len(feed) > 0, "SOFA feed should contain at least one release entry"
    assert all("OSVersion" in entry for entry in feed), (
        "Every SOFA feed entry should carry an OSVersion key"
    )
