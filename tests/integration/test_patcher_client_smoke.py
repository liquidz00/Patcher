"""
Integration smoke tests: PatcherClient end-to-end against the integration instance.

dummy.jamfcloud.com lacks patch management software titles, so the
patch-data-heavy operations (analyze, export with real titles) aren't
testable end-to-end here. Those flows are exercised against synthetic
PatchTitle data in ``scripts/smoke_test.py``.

This module verifies:
  - PatcherClient constructs against the live instance with collaborators wired.
  - The async context manager releases resources cleanly.
  - ``fetch_patches()`` runs without error against the live instance
    (returns an empty list against dummy if no titles are configured).
"""

from __future__ import annotations

import pytest
from src.patcher import JamfClient, PatcherAPIClient
from src.patcher.core.data_manager import DataManager
from src.patcher.core.models.patch import PatchTitle


@pytest.mark.integration
@pytest.mark.asyncio
async def test_patcher_client_wires_collaborators(integration_patcher_client) -> None:
    """PatcherClient exposes the expected attached collaborators after construction."""
    p = integration_patcher_client
    assert isinstance(p.jamf, JamfClient), "patcher.jamf should be a JamfClient"
    assert isinstance(p.api, PatcherAPIClient), "patcher.api should be a PatcherAPIClient"
    assert isinstance(p.data, DataManager), "patcher.data should be a DataManager"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_patches_runs_against_live_instance(integration_patcher_client) -> None:
    """
    fetch_patches completes a real Jamf round-trip without raising.

    Against dummy.jamfcloud.com this typically returns ``[]`` because no
    patch management titles are configured. Pointing the suite at a real
    instance via ``PATCHER_INTEGRATION_*`` env vars exercises the full
    matching pipeline.
    """
    titles = await integration_patcher_client.fetch_patches()

    assert isinstance(titles, list)
    if titles:
        assert all(isinstance(t, PatchTitle) for t in titles), (
            "Every returned item should be a PatchTitle"
        )
