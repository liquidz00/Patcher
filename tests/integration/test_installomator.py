"""
Integration tests: Installomator label discovery and fetch against the live repo.

These tests don't require Jamf credentials. A bare ``InstallomatorClient()``
fetches directly from the Installomator GitHub repo via raw.githubusercontent.com.
"""

from __future__ import annotations

import pytest
from src.patcher import InstallomatorClient
from src.patcher.core.models.label import Label


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_available_labels_returns_set() -> None:
    """Labels.txt fetch returns a non-empty set of script names, with 'firefox' present."""
    iom = InstallomatorClient()
    try:
        names = await iom.list_available_labels()
    finally:
        await iom.api.aclose()

    assert isinstance(names, set)
    assert len(names) > 100, f"Expected hundreds of labels, got {len(names)}"
    # 'firefox' is a long-standing Installomator label, safe sanity check
    assert "firefox" in names, "'firefox' should be in the Installomator label catalog"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_label_returns_label_object() -> None:
    """Fetching the 'firefox' label returns a parsed ``Label`` model."""
    iom = InstallomatorClient()
    try:
        label = await iom.get_label("firefox")
    finally:
        await iom.api.aclose()

    assert label is not None, "firefox label should exist and parse"
    assert isinstance(label, Label)
    assert label.expected_team_id, "Label should carry an expected_team_id"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_label_returns_none_for_unknown() -> None:
    """Fetching a nonexistent label returns None instead of raising (404 absorbed)."""
    iom = InstallomatorClient()
    try:
        label = await iom.get_label("this-label-definitely-does-not-exist-xyz-12345")
    finally:
        await iom.api.aclose()

    assert label is None
