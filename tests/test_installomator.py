"""Tests for src/patcher/utils/installomator.py.

The Installomator class can't be exercised against a live Jamf instance, so
every test here mocks ``api.fetch_text`` (the httpx-based GET helper) and
``api.get_app_names`` (the Jamf-side patch-title → app-name resolver). The
test surface validates:

- Labels.txt discovery + caching
- Single-label fetch with disk + instance cache
- Bulk fetch (specific names AND eager-all)
- Team ID filtering
- The full match() pipeline end-to-end
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from src.patcher.models.patch import PatchTitle
from src.patcher.utils.exceptions import APIResponseError
from src.patcher.utils.installomator import Installomator

# ---------------------------------------------------------------------- #
# Fixtures
# ---------------------------------------------------------------------- #


def _sample_fragment(
    *,
    name: str = "Google Chrome",
    team_id: str = "EQHXZ8M8AV",
    label_type: str = "pkg",
    url: str = "https://dl.google.com/chrome.pkg",
) -> str:
    """Return the raw content of a minimal but valid Installomator fragment."""
    return (
        f"{name.lower().replace(' ', '')})\n"
        f'    name="{name}"\n'
        f'    type="{label_type}"\n'
        f'    downloadURL="{url}"\n'
        f'    expectedTeamID="{team_id}"\n'
        f"    ;;"
    )


@pytest.fixture
def iom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Installomator:
    """Return an Installomator instance with isolated cache paths and a mocked api.

    Installomator's constructor builds its own ApiClient internally, which
    triggers TokenManager.attach_client() → keyring.get_password(). On Linux
    CI runners there's no keyring backend available, so the chain raises
    NoKeyringError before the test can swap in a mock.

    Patching ApiClient at the installomator module level intercepts the chain
    at construction time, leaving us free to set `instance.api = AsyncMock()`
    in the body below as the actual test surface.
    """
    monkeypatch.setattr(
        "src.patcher.utils.installomator.ApiClient",
        lambda **kwargs: AsyncMock(),
    )
    instance = Installomator()
    instance.label_path = tmp_path / ".labels"
    instance.review_file = tmp_path / "unmatched_apps.json"
    instance.api = AsyncMock()
    return instance


# ---------------------------------------------------------------------- #
# list_available_labels
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_list_available_labels_parses_labels_txt(iom: Installomator) -> None:
    iom.api.fetch_text.return_value = "googlechrome\n1password8\nzulujdk8\n"

    result = await iom.list_available_labels()

    assert result == {"googlechrome", "1password8", "zulujdk8"}
    iom.api.fetch_text.assert_called_once()
    # Verify the URL we hit is the explicit refs/heads/main form
    called_url = iom.api.fetch_text.call_args[0][0]
    assert "Labels.txt" in called_url
    assert "refs/heads/main" in called_url


@pytest.mark.asyncio
async def test_list_available_labels_ignores_blank_and_comment_lines(iom: Installomator) -> None:
    iom.api.fetch_text.return_value = "# comment\ngooglechrome\n\n1password8\n   \n"

    result = await iom.list_available_labels()

    assert result == {"googlechrome", "1password8"}


@pytest.mark.asyncio
async def test_list_available_labels_caches_result(iom: Installomator) -> None:
    iom.api.fetch_text.return_value = "googlechrome\n"

    first = await iom.list_available_labels()
    second = await iom.list_available_labels()

    assert first == second
    assert iom.api.fetch_text.call_count == 1  # cached on the instance


@pytest.mark.asyncio
async def test_list_available_labels_raises_on_fetch_failure(iom: Installomator) -> None:
    from src.patcher.utils.exceptions import PatcherError

    iom.api.fetch_text.side_effect = APIResponseError(
        "Server error", url="https://example.com/Labels.txt", status_code=500
    )

    with pytest.raises(PatcherError, match="Labels.txt"):
        await iom.list_available_labels()


# ---------------------------------------------------------------------- #
# get_label
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_label_fetches_and_caches(iom: Installomator) -> None:
    iom.api.fetch_text.return_value = _sample_fragment()

    label = await iom.get_label("googlechrome")

    assert label is not None
    assert label.name == "Google Chrome"
    assert label.installomatorLabel == "googlechrome"
    # Cached on instance: subsequent call doesn't refetch
    label_again = await iom.get_label("googlechrome")
    assert label_again is label
    assert iom.api.fetch_text.call_count == 1


@pytest.mark.asyncio
async def test_get_label_writes_to_disk_cache(iom: Installomator) -> None:
    iom.api.fetch_text.return_value = _sample_fragment()

    await iom.get_label("googlechrome")

    cached_path = iom.label_path / "googlechrome.sh"
    assert cached_path.exists()
    assert "Google Chrome" in cached_path.read_text()


@pytest.mark.asyncio
async def test_get_label_reads_from_disk_cache_first(iom: Installomator) -> None:
    iom.label_path.mkdir(parents=True, exist_ok=True)
    (iom.label_path / "googlechrome.sh").write_text(_sample_fragment())

    label = await iom.get_label("googlechrome")

    assert label is not None
    assert label.name == "Google Chrome"
    iom.api.fetch_text.assert_not_called()


@pytest.mark.asyncio
async def test_get_label_returns_none_on_404(iom: Installomator) -> None:
    iom.api.fetch_text.side_effect = APIResponseError(
        "Not found", url="https://example.com/x.sh", status_code=404, not_found=True
    )

    label = await iom.get_label("nonexistent-app")

    assert label is None


@pytest.mark.asyncio
async def test_get_label_returns_none_on_ignored_team_id(iom: Installomator) -> None:
    # LL3KBL2M3A is in IGNORED_TEAMS (lcadvancedvpnclient)
    iom.api.fetch_text.return_value = _sample_fragment(name="LC AdvancedVPN", team_id="LL3KBL2M3A")

    label = await iom.get_label("lcadvancedvpnclient")

    assert label is None


@pytest.mark.asyncio
async def test_get_label_is_case_insensitive(iom: Installomator) -> None:
    iom.api.fetch_text.return_value = _sample_fragment()

    label_lower = await iom.get_label("googlechrome")
    label_upper = await iom.get_label("GOOGLECHROME")

    assert label_lower is label_upper  # same cached instance


# ---------------------------------------------------------------------- #
# get_labels
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_labels_with_explicit_names(iom: Installomator) -> None:
    iom.api.fetch_text.return_value = _sample_fragment()

    labels = await iom.get_labels({"googlechrome", "firefox"})

    assert len(labels) == 2
    assert iom.api.fetch_text.call_count == 2  # one per name


@pytest.mark.asyncio
async def test_get_labels_with_none_fetches_all(iom: Installomator) -> None:
    """When `names=None`, fetches every label listed in Labels.txt."""

    async def fetch_text_side_effect(url: str, **kwargs) -> str:
        if url.endswith("/Labels.txt"):
            return "googlechrome\nfirefox\n"
        return _sample_fragment()

    iom.api.fetch_text.side_effect = fetch_text_side_effect

    labels = await iom.get_labels()

    assert len(labels) == 2
    # 1 call for Labels.txt + 2 fragment fetches
    assert iom.api.fetch_text.call_count == 3


@pytest.mark.asyncio
async def test_get_labels_with_empty_iterable(iom: Installomator) -> None:
    labels = await iom.get_labels([])

    assert labels == []
    iom.api.fetch_text.assert_not_called()


@pytest.mark.asyncio
async def test_get_labels_skips_failed_fetches(iom: Installomator) -> None:
    """A failed fetch for one label doesn't break the batch."""

    async def fetch_text_side_effect(url: str, **kwargs) -> str:
        if "googlechrome.sh" in url:
            return _sample_fragment()
        raise APIResponseError("Not found", url=url, status_code=404, not_found=True)

    iom.api.fetch_text.side_effect = fetch_text_side_effect

    labels = await iom.get_labels(["googlechrome", "nonexistent"])

    assert len(labels) == 1
    assert labels[0].name == "Google Chrome"


# ---------------------------------------------------------------------- #
# Matching helpers
# ---------------------------------------------------------------------- #


def test_normalize_lowercases_strips_spaces_and_dots() -> None:
    assert Installomator._normalize("Google Chrome") == "googlechrome"
    assert Installomator._normalize("Node.js") == "nodejs"
    assert Installomator._normalize("1Password 7") == "1password7"


def test_match_directly_direct_hit(iom: Installomator) -> None:
    matched = iom._match_directly(["googlechrome"], {"googlechrome", "firefox"})
    assert matched == ["googlechrome"]


def test_match_directly_normalized_hit(iom: Installomator) -> None:
    matched = iom._match_directly(["Google Chrome"], {"googlechrome"})
    assert matched == ["googlechrome"]


def test_match_directly_no_duplicates(iom: Installomator) -> None:
    """Direct + normalized matches against the same label shouldn't double up."""
    matched = iom._match_directly(["googlechrome", "Google Chrome"], {"googlechrome"})
    assert matched == ["googlechrome"]


def test_match_directly_no_hit(iom: Installomator) -> None:
    matched = iom._match_directly(["unknown-app"], {"googlechrome"})
    assert matched == []


def test_match_fuzzy_hits_above_threshold(iom: Installomator) -> None:
    matched = iom._match_fuzzy(["google chrome"], {"googlechrome"})
    # rapidfuzz.ratio("google chrome", "googlechrome") is high enough to clear 85
    assert matched == ["googlechrome"]


def test_match_fuzzy_misses_below_threshold(iom: Installomator) -> None:
    matched = iom._match_fuzzy(["zzz-unrelated"], {"googlechrome"})
    assert matched == []


# ---------------------------------------------------------------------- #
# match() — full pipeline
# ---------------------------------------------------------------------- #


def _make_patch_title(title: str, title_id: str = "1") -> PatchTitle:
    return PatchTitle(
        title=title,
        title_id=title_id,
        released="2024-01-01",
        hosts_patched=10,
        missing_patch=2,
        latest_version="1.0.0",
    )


@pytest.mark.asyncio
async def test_match_attaches_labels_to_matched_titles(iom: Installomator) -> None:
    iom.api.get_app_names = AsyncMock(
        return_value=[{"Patch": "Google Chrome", "App Names": ["Google Chrome"]}]
    )

    async def fetch_text_side_effect(url: str, **kwargs) -> str:
        if url.endswith("/Labels.txt"):
            return "googlechrome\n"
        return _sample_fragment()

    iom.api.fetch_text.side_effect = fetch_text_side_effect

    patch_titles = [_make_patch_title("Google Chrome")]
    await iom.match(patch_titles)

    assert len(patch_titles[0].install_label) == 1
    assert patch_titles[0].install_label[0].name == "Google Chrome"


@pytest.mark.asyncio
async def test_match_persists_unmatched_apps(iom: Installomator) -> None:
    iom.api.get_app_names = AsyncMock(
        return_value=[{"Patch": "Mystery App", "App Names": ["Mystery App"]}]
    )

    async def fetch_text_side_effect(url: str, **kwargs) -> str:
        if url.endswith("/Labels.txt"):
            return "googlechrome\n"
        return _sample_fragment()

    iom.api.fetch_text.side_effect = fetch_text_side_effect

    patch_titles = [_make_patch_title("Mystery App")]
    await iom.match(patch_titles)

    assert iom.review_file.exists()
    import json

    with iom.review_file.open() as f:
        review = json.load(f)
    assert review == [{"Patch": "Mystery App", "App Names": ["Mystery App"]}]


@pytest.mark.asyncio
async def test_match_skips_ignored_title_patterns(iom: Installomator) -> None:
    """Apple macOS *, Oracle Java SE *, etc. should be skipped wholesale."""
    iom.api.get_app_names = AsyncMock(
        return_value=[
            {"Patch": "Apple macOS Ventura", "App Names": ["macOS Ventura"]},
            {"Patch": "Apple Safari", "App Names": ["Safari"]},
        ]
    )
    iom.api.fetch_text.return_value = "googlechrome\n"  # Labels.txt only — no fragments fetched

    patch_titles = [
        _make_patch_title("Apple macOS Ventura"),
        _make_patch_title("Apple Safari", title_id="2"),
    ]
    await iom.match(patch_titles)

    for pt in patch_titles:
        assert pt.install_label == []
    # Only Labels.txt was fetched; ignored titles never trigger fragment fetches
    assert iom.api.fetch_text.call_count == 1


@pytest.mark.asyncio
async def test_match_second_pass_finds_normalized_title(iom: Installomator) -> None:
    """A title with no app_name matches should still match via normalized title text."""
    iom.api.get_app_names = AsyncMock(
        return_value=[{"Patch": "Google Chrome", "App Names": ["totally-unrelated"]}]
    )

    async def fetch_text_side_effect(url: str, **kwargs) -> str:
        if url.endswith("/Labels.txt"):
            return "googlechrome\n"
        return _sample_fragment()

    iom.api.fetch_text.side_effect = fetch_text_side_effect

    patch_titles = [_make_patch_title("Google Chrome")]
    await iom.match(patch_titles)

    # Second-pass picked it up by normalizing the patch title text
    assert len(patch_titles[0].install_label) == 1
    assert patch_titles[0].install_label[0].name == "Google Chrome"


@pytest.mark.asyncio
async def test_match_does_nothing_on_404_from_get_app_names(iom: Installomator) -> None:
    """If get_app_names raises a 404 APIResponseError, match returns silently."""
    from src.patcher.utils.exceptions import APIResponseError

    err = APIResponseError("not found", status_code=404, error="404", not_found=True)
    iom.api.get_app_names = AsyncMock(side_effect=err)

    patch_titles = [_make_patch_title("Google Chrome")]
    await iom.match(patch_titles)  # must not raise

    assert patch_titles[0].install_label == []
