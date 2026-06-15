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
from src.patcher.core import matching
from src.patcher.core.exceptions import APIResponseError, InstallomatorWarning
from src.patcher.core.matching import (
    match_directly,
    match_fuzzy,
    match_titles,
    normalize_name,
)
from src.patcher.core.models.patch import PatchTitle


def _patch_title(title: str, name_id: str | None = None) -> PatchTitle:
    return PatchTitle(
        title=title,
        title_id="42",
        released="2026-01-01",
        hosts_patched=1,
        missing_patch=1,
        latest_version="1.0",
        name_id=name_id,
    )


def _app(slug: str, name: str = "Test App", sources: list[str] | None = None) -> App:
    return App(slug=slug, name=name, sources=sources or ["installomator"])


def _api_with(apps_by_source: dict[str, list[App]]) -> AsyncMock:
    """
    Build a mock ``PatcherAPIClient`` whose ``list_apps`` answers per-source.

    Returns the source's full app list on the first page (``offset == 0``) and
    an empty list thereafter, matching how :func:`_fetch_catalog_apps` pages
    until a short page. A dual-source app should appear under both source keys,
    since the real ``/apps`` endpoint returns it for either source filter.
    """
    api = AsyncMock()

    def _list(*, source=None, limit=1000, offset=0, vendor=None, exclude_source=None):
        if offset > 0:
            return []
        return apps_by_source.get(source, [])

    api.list_apps.side_effect = _list
    return api


class TestNormalizeName:
    def test_lowercases(self):
        assert normalize_name("Google Chrome") == "googlechrome"

    def test_strips_dots(self):
        assert normalize_name("Node.js") == "nodejs"

    def test_strips_all_punctuation(self):
        # Canonical form shared with the API: every non-alphanumeric is stripped.
        assert normalize_name("Adobe Acrobat (64-bit)") == "adobeacrobat64bit"
        assert normalize_name(None) == ""


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
    async def test_direct_match_records_installomator_slug(self, tmp_path):
        title = _patch_title("Firefox")
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox", name="Firefox")]
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Firefox", "App Names": ["Firefox"]}]

        await match_titles([title], jamf=jamf, api=api, review_file=tmp_path / "review.json")

        api.list_apps.assert_awaited_once_with(source="installomator", limit=1000, offset=0)
        assert title.installomator == ["firefox"]
        assert title.sources == {"installomator": ["firefox"]}

    @pytest.mark.asyncio
    async def test_no_match_writes_review_file(self, tmp_path):
        title = _patch_title("Acme Reader")
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox")]
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Acme Reader", "App Names": ["Acme Reader"]}]
        review_file = tmp_path / "review.json"

        with pytest.warns(InstallomatorWarning):
            await match_titles([title], jamf=jamf, api=api, review_file=review_file)

        assert title.installomator == []
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

        assert title.installomator == []
        # Jamf side still gets queried, but no match attempt is made for the
        # ignored title (no entry appears in unmatched_apps either).

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ignored", ["Adobe Photoshop 2024", "Jamf Self Service for macOS"])
    async def test_policy_vendor_globs_skip_titles(self, tmp_path, ignored):
        title = _patch_title(ignored)
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox")]
        jamf = AsyncMock()
        jamf.get_app_names.return_value = []
        review_file = tmp_path / "review.json"

        await match_titles([title], jamf=jamf, api=api, review_file=review_file)

        assert title.installomator == []
        assert not review_file.exists() or ignored not in review_file.read_text()

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

        assert title.installomator == ["googlechrome"]

    @pytest.mark.asyncio
    async def test_api_failure_returns_early(self, tmp_path):
        title = _patch_title("Firefox")
        api = AsyncMock()
        api.list_apps.side_effect = APIResponseError("API down", status_code=503)
        jamf = AsyncMock()

        # No raise — log + return.
        await match_titles([title], jamf=jamf, api=api, review_file=tmp_path / "review.json")

        jamf.get_app_names.assert_not_called()
        assert title.installomator == []

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

        assert title.installomator == []

    @pytest.mark.asyncio
    async def test_review_file_none_skips_persistence(self, tmp_path, monkeypatch):
        """When review_file=None, no JSON is written even for unmatched titles."""
        title = _patch_title("Acme Reader")
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox")]
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Acme Reader", "App Names": ["Acme Reader"]}]

        with pytest.warns(InstallomatorWarning):
            await match_titles([title], jamf=jamf, api=api, review_file=None)

        # tmp_path is empty — review file was not written anywhere.
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.asyncio
    async def test_caller_ignored_titles_skip_matching(self):
        """A title matching a caller-supplied pattern is skipped despite a catalog hit."""
        title = _patch_title("Acme Corp Viewer")
        api = _api_with({"installomator": [_app("acmecorpviewer", name="Acme Corp Viewer")]})
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [
            {"Patch": "Acme Corp Viewer", "App Names": ["Acme Corp Viewer"]}
        ]

        await match_titles([title], jamf=jamf, api=api, review_file=None, ignored_titles=["Acme *"])

        assert title.installomator == []


class TestHomebrewMatching:
    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::src.patcher.core.exceptions.InstallomatorWarning")
    async def test_off_by_default_ignores_cask_only_slug(self, tmp_path):
        """With include_homebrew unset, only the installomator source is fetched."""
        title = _patch_title("Rectangle")
        api = _api_with({"homebrew_cask": [_app("rectangle", sources=["homebrew_cask"])]})
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Rectangle", "App Names": ["Rectangle"]}]

        await match_titles([title], jamf=jamf, api=api, review_file=tmp_path / "r.json")

        # homebrew_cask source was never queried; the cask-only slug is invisible.
        api.list_apps.assert_awaited_once_with(source="installomator", limit=1000, offset=0)
        assert title.sources == {}

    @pytest.mark.asyncio
    async def test_cask_only_populates_homebrew_source(self, tmp_path):
        title = _patch_title("Rectangle")
        api = _api_with({"homebrew_cask": [_app("rectangle", sources=["homebrew_cask"])]})
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Rectangle", "App Names": ["Rectangle"]}]

        await match_titles(
            [title], jamf=jamf, api=api, review_file=tmp_path / "r.json", include_homebrew=True
        )

        assert title.installomator == []
        assert title.homebrew_cask == ["rectangle"]

    @pytest.mark.asyncio
    async def test_dual_source_populates_both(self, tmp_path):
        dual = _app("firefox", name="Firefox", sources=["installomator", "homebrew_cask"])
        title = _patch_title("Firefox")
        api = _api_with({"installomator": [dual], "homebrew_cask": [dual]})
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Firefox", "App Names": ["Firefox"]}]

        await match_titles(
            [title], jamf=jamf, api=api, review_file=tmp_path / "r.json", include_homebrew=True
        )

        assert title.installomator == ["firefox"]
        assert title.homebrew_cask == ["firefox"]

    @pytest.mark.asyncio
    async def test_dual_source_with_toggle_off_records_all_sources(self, tmp_path):
        """A dual-source slug matched via Installomator still records every source it carries."""
        dual = _app("firefox", name="Firefox", sources=["installomator", "homebrew_cask"])
        title = _patch_title("Firefox")
        api = _api_with({"installomator": [dual]})
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Firefox", "App Names": ["Firefox"]}]

        await match_titles([title], jamf=jamf, api=api, review_file=tmp_path / "r.json")

        # Coverage surfaces for free: the cask source is recorded even though the
        # candidate set was Installomator-only (toggle off).
        assert title.installomator == ["firefox"]
        assert title.homebrew_cask == ["firefox"]

    @pytest.mark.asyncio
    async def test_second_pass_routes_cask(self, tmp_path):
        """Second-pass (patch-title-text) matches also route by provenance."""
        title = _patch_title("Google Chrome")
        api = _api_with({"homebrew_cask": [_app("googlechrome", sources=["homebrew_cask"])]})
        jamf = AsyncMock()
        # No app names — forces the second pass to normalize the patch title text.
        jamf.get_app_names.return_value = [{"Patch": "Google Chrome", "App Names": []}]

        await match_titles(
            [title], jamf=jamf, api=api, review_file=tmp_path / "r.json", include_homebrew=True
        )

        assert title.installomator == []
        assert title.homebrew_cask == ["googlechrome"]

    @pytest.mark.asyncio
    async def test_paginates_past_page_size(self, tmp_path, monkeypatch):
        """_fetch_catalog_apps keeps paging until a short page signals the end."""
        monkeypatch.setattr(matching, "_CATALOG_PAGE_SIZE", 2)
        # Three installomator apps across two pages of size 2.
        pages = [
            [_app("a"), _app("b")],
            [_app("c")],
        ]
        api = AsyncMock()

        def _list(*, source=None, limit=2, offset=0, vendor=None, exclude_source=None):
            return pages[offset // 2] if offset // 2 < len(pages) else []

        api.list_apps.side_effect = _list
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "C App", "App Names": ["c"]}]
        title = _patch_title("C App")

        await match_titles([title], jamf=jamf, api=api, review_file=tmp_path / "r.json")

        # Two list_apps calls: offset 0 (full page) then offset 2 (short page → stop).
        assert api.list_apps.await_count == 2
        assert title.installomator == ["c"]


class TestDeterministicMatch:
    @pytest.mark.asyncio
    async def test_name_id_exact_match_attaches_index_slugs(self):
        """A title whose name_id is in the index attaches those slugs, no fuzzing."""
        title = _patch_title("Mozilla Firefox", name_id="0B3")
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox", name="Firefox")]
        api.get_jamf_index.return_value = {"0B3": ["firefox"]}
        jamf = AsyncMock()
        jamf.get_app_names.return_value = []  # no app-name data — proves we didn't fuzzy-match

        await match_titles([title], jamf=jamf, api=api, review_file=None)

        assert title.installomator == ["firefox"]

    @pytest.mark.asyncio
    async def test_name_id_not_indexed_falls_back_to_fuzzy(self):
        title = _patch_title("Mozilla Firefox", name_id="ZZZ")  # code not in the index
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox", name="Firefox")]
        api.get_jamf_index.return_value = {"0B3": ["firefox"]}
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Mozilla Firefox", "App Names": ["Firefox"]}]

        await match_titles([title], jamf=jamf, api=api, review_file=None)

        assert title.installomator == ["firefox"]

    @pytest.mark.asyncio
    async def test_index_slug_absent_from_catalog_falls_back_to_fuzzy(self):
        """A code resolving only to a slug outside the fetched set falls through."""
        title = _patch_title("Mozilla Firefox", name_id="0B3")
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox", name="Firefox")]  # available = {firefox}
        api.get_jamf_index.return_value = {"0B3": ["firefox-cask-only"]}  # not in available
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Mozilla Firefox", "App Names": ["Firefox"]}]

        await match_titles([title], jamf=jamf, api=api, review_file=None)

        assert title.installomator == ["firefox"]

    @pytest.mark.asyncio
    async def test_index_unavailable_degrades_to_fuzzy(self):
        title = _patch_title("Firefox", name_id="0B3")
        api = AsyncMock()
        api.list_apps.return_value = [_app("firefox", name="Firefox")]
        api.get_jamf_index.side_effect = APIResponseError("index endpoint missing")
        jamf = AsyncMock()
        jamf.get_app_names.return_value = [{"Patch": "Firefox", "App Names": ["Firefox"]}]

        await match_titles([title], jamf=jamf, api=api, review_file=None)

        assert title.installomator == ["firefox"]
