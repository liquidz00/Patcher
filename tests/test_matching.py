"""
Tests for :mod:`patcher.core.matching` — the API-backed matching pipeline.

Algorithm tests (direct / fuzzy / normalize) are pure functions, exercised
directly. The orchestrator :func:`match_titles` is exercised with mocked
``JamfClient`` and ``PatcherAPIClient`` so the test surface validates the
pipeline shape (API call, Jamf call, slug set construction, match
attachment, second pass) without standing up real HTTP infrastructure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from src.patcher.clients.patcher_api import App
from src.patcher.core.exceptions import APIResponseError
from src.patcher.core.matching import (
    match_directly,
    match_fuzzy,
    match_titles,
    normalize_name,
)
from src.patcher.core.models.patch import PatchTitle


def _patch_title(title: str) -> PatchTitle:
    return PatchTitle(
        title=title,
        title_id="42",
        released="2026-01-01",
        hosts_patched=1,
        missing_patch=1,
        latest_version="1.0",
    )


def _app(slug: str, name: str = "Test App") -> App:
    return App(slug=slug, name=name, sources=["installomator"])


class TestNormalizeName:
    def test_lowercases(self):
        assert normalize_name("Google Chrome") == "googlechrome"

    def test_strips_dots(self):
        assert normalize_name("Node.js") == "nodejs"


class TestMatchDirectly:
    def test_lowercase_hit(self):
        assert match_directly(["Firefox"], {"firefox"}) == ["firefox"]

    def test_normalized_hit(self):
        assert match_directly(["Node.js"], {"nodejs"}) == ["nodejs"]

    def test_no_duplicates(self):
        assert match_directly(["Firefox", "firefox"], {"firefox"}) == ["firefox"]

    def test_miss(self):
        assert match_directly(["Acme"], {"firefox"}) == []


class TestMatchFuzzy:
    def test_hit_above_threshold(self):
        # "google chrome" vs "googlechrome" is a near-perfect ratio.
        assert "googlechrome" in match_fuzzy(["Google Chrome"], {"googlechrome", "firefox"})

    def test_miss_below_threshold(self):
        assert match_fuzzy(["Apple Pages"], {"zoom", "slack"}, threshold=95) == []


class TestMatchTitlesPipeline:
    @pytest.mark.asyncio
    async def test_direct_match_attaches_label_stub(self, tmp_path):
        title = _patch_title("Firefox")
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox", name="Firefox")]
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Firefox", "App Names": ["Firefox"]}]

        await match_titles([title], jamf=jamf, api=api, review_file=tmp_path / "review.json")

        api.list_apps.assert_awaited_once_with(source="installomator", limit=1000)
        assert len(title.install_label) == 1
        assert title.install_label[0].installomator_label == "firefox"
        assert title.install_label[0].name == "Firefox"

    @pytest.mark.asyncio
    async def test_no_match_writes_review_file(self, tmp_path):
        title = _patch_title("Acme Reader")
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox")]
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Acme Reader", "App Names": ["Acme Reader"]}]
        review_file = tmp_path / "review.json"

        await match_titles([title], jamf=jamf, api=api, review_file=review_file)

        assert title.install_label == []
        assert review_file.exists()
        assert "Acme Reader" in review_file.read_text()

    @pytest.mark.asyncio
    async def test_ignored_title_skipped(self, tmp_path):
        title = _patch_title("Apple macOS Sonoma")
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox")]
        jamf = AsyncMock()
        # get_app_names returns nothing for this title — it's been filtered.
        jamf.get_app_names.return_value = []

        await match_titles([title], jamf=jamf, api=api, review_file=tmp_path / "review.json")

        assert title.install_label == []
        # Jamf side still gets queried, but no match attempt is made for the
        # ignored title (no entry appears in unmatched_apps either).

    @pytest.mark.asyncio
    async def test_second_pass_normalizes_patch_title_directly(self, tmp_path):
        """When Jamf provides no app names, second pass uses the patch title text."""
        title = _patch_title("Google Chrome")
        api = AsyncMock()
        api.list_apps.return_value = [_app("googlechrome")]
        jamf = AsyncMock()
        # No app names returned, so first pass marks unmatched. Second pass
        # normalizes "Google Chrome" → "googlechrome" and finds the slug.
        jamf.get_app_names.return_value = [{"Patch": "Google Chrome", "App Names": []}]

        await match_titles([title], jamf=jamf, api=api, review_file=tmp_path / "review.json")

        assert len(title.install_label) == 1
        assert title.install_label[0].installomator_label == "googlechrome"

    @pytest.mark.asyncio
    async def test_api_failure_returns_early(self, tmp_path):
        title = _patch_title("Firefox")
        api = AsyncMock()
        api.list_apps.side_effect = APIResponseError("API down", status_code=503)
        jamf = AsyncMock()

        # No raise — log + return.
        await match_titles([title], jamf=jamf, api=api, review_file=tmp_path / "review.json")

        jamf.get_app_names.assert_not_called()
        assert title.install_label == []

    @pytest.mark.asyncio
    async def test_jamf_404_returns_silently(self, tmp_path):
        title = _patch_title("Firefox")
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox")]
        jamf = AsyncMock()
        jamf.get_app_names.side_effect = APIResponseError(
            "no app names", status_code=404, not_found=True
        )

        await match_titles([title], jamf=jamf, api=api, review_file=tmp_path / "review.json")

        assert title.install_label == []

    @pytest.mark.asyncio
    async def test_review_file_none_skips_persistence(self, tmp_path, monkeypatch):
        """When review_file=None, no JSON is written even for unmatched titles."""
        title = _patch_title("Acme Reader")
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox")]
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Acme Reader", "App Names": ["Acme Reader"]}]

        await match_titles([title], jamf=jamf, api=api, review_file=None)

        # tmp_path is empty — review file was not written anywhere.
        assert list(tmp_path.iterdir()) == []
