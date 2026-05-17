"""
Tests for src/patcher/utils/installomator.py.

The InstallomatorClient class can't be exercised against a live Jamf instance, so
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

import httpx
import pytest
from src.patcher.client.jamf import JamfClient
from src.patcher.core.exceptions import APIResponseError
from src.patcher.core.installomator import (
    InstallomatorClient,
    InvalidOutput,
    Resolved,
    Unresolvable,
    _exec_awk,
    _exec_cut,
    _exec_grep,
    _exec_head,
    _exec_sed,
    _exec_sort,
    _exec_tail,
    _exec_tr,
    _exec_uniq,
    _parse_field_spec,
    _split_pipeline,
    _tokenize,
    looks_like_clean_http_url,
    resolve,
)
from src.patcher.core.models.patch import PatchTitle


def _sample_fragment(
    *,
    name: str = "Google Chrome",
    team_id: str = "EQHXZ8M8AV",
    label_type: str = "pkg",
    url: str = "https://dl.google.com/chrome.pkg",
) -> str:
    """Return the raw content of a minimal but valid InstallomatorClient fragment."""
    return (
        f"{name.lower().replace(' ', '')})\n"
        f'    name="{name}"\n'
        f'    type="{label_type}"\n'
        f'    downloadURL="{url}"\n'
        f'    expectedTeamID="{team_id}"\n'
        f"    ;;"
    )


@pytest.fixture
def iom(tmp_path: Path) -> InstallomatorClient:
    """
    Return an InstallomatorClient with isolated cache paths and a mocked api.

    Constructed bare — no Jamf credentials needed (the default ``HTTPClient``
    has no keyring touchpoint). The api attribute is then replaced with an
    ``AsyncMock(spec=JamfClient)`` so ``match()`` sees a JamfClient-shaped
    object (it asserts on type to surface a clear error for callers passing
    a plain ``HTTPClient`` to a method that requires Jamf endpoints).
    """
    instance = InstallomatorClient()
    instance.label_path = tmp_path / ".labels"
    instance.review_file = tmp_path / "unmatched_apps.json"
    instance.api = AsyncMock(spec=JamfClient)
    return instance


def test_bare_construction_does_not_require_jamf_creds() -> None:
    """
    ``InstallomatorClient()`` with no args must construct cleanly even when no
    Jamf credentials exist anywhere (keyring, in-memory, env). Library callers
    using the client purely for label discovery / fetch shouldn't have to
    stand up Jamf auth they don't need.
    """
    from src.patcher.client import HTTPClient

    iom = InstallomatorClient()
    assert isinstance(iom.api, HTTPClient)


@pytest.mark.asyncio
async def test_match_raises_without_jamf_client() -> None:
    """
    ``match()`` requires a JamfClient (it calls ``get_app_names``). When the
    default ``HTTPClient`` is in place, surface a clear ``PatcherError``
    pointing the caller at the fix rather than a cryptic AttributeError.
    """
    from src.patcher.core.exceptions import PatcherError

    iom = InstallomatorClient()
    with pytest.raises(PatcherError, match="requires a configured JamfClient"):
        await iom.match([])


@pytest.mark.asyncio
async def test_list_available_labels_parses_labels_txt(iom: InstallomatorClient) -> None:
    iom.api.fetch_text.return_value = "googlechrome\n1password8\nzulujdk8\n"

    result = await iom.list_available_labels()

    assert result == {"googlechrome", "1password8", "zulujdk8"}
    iom.api.fetch_text.assert_called_once()
    # Verify the URL we hit is the explicit refs/heads/main form
    called_url = iom.api.fetch_text.call_args[0][0]
    assert "Labels.txt" in called_url
    assert "refs/heads/main" in called_url


@pytest.mark.asyncio
async def test_list_available_labels_ignores_blank_and_comment_lines(
    iom: InstallomatorClient,
) -> None:
    iom.api.fetch_text.return_value = "# comment\ngooglechrome\n\n1password8\n   \n"

    result = await iom.list_available_labels()

    assert result == {"googlechrome", "1password8"}


@pytest.mark.asyncio
async def test_list_available_labels_caches_result(iom: InstallomatorClient) -> None:
    iom.api.fetch_text.return_value = "googlechrome\n"

    first = await iom.list_available_labels()
    second = await iom.list_available_labels()

    assert first == second
    assert iom.api.fetch_text.call_count == 1  # cached on the instance


@pytest.mark.asyncio
async def test_list_available_labels_raises_on_fetch_failure(iom: InstallomatorClient) -> None:
    from src.patcher.core.exceptions import PatcherError

    iom.api.fetch_text.side_effect = APIResponseError(
        "Server error", url="https://example.com/Labels.txt", status_code=500
    )

    with pytest.raises(PatcherError, match="Labels.txt"):
        await iom.list_available_labels()


@pytest.mark.asyncio
async def test_get_label_fetches_and_caches(iom: InstallomatorClient) -> None:
    iom.api.fetch_text.return_value = _sample_fragment()

    label = await iom.get_label("googlechrome")

    assert label is not None
    assert label.name == "Google Chrome"
    assert label.installomator_label == "googlechrome"
    # Cached on instance: subsequent call doesn't refetch
    label_again = await iom.get_label("googlechrome")
    assert label_again is label
    assert iom.api.fetch_text.call_count == 1


@pytest.mark.asyncio
async def test_get_label_writes_to_disk_cache(iom: InstallomatorClient) -> None:
    iom.api.fetch_text.return_value = _sample_fragment()

    await iom.get_label("googlechrome")

    cached_path = iom.label_path / "googlechrome.sh"
    assert cached_path.exists()
    assert "Google Chrome" in cached_path.read_text()


@pytest.mark.asyncio
async def test_get_label_reads_from_disk_cache_first(iom: InstallomatorClient) -> None:
    iom.label_path.mkdir(parents=True, exist_ok=True)
    (iom.label_path / "googlechrome.sh").write_text(_sample_fragment())

    label = await iom.get_label("googlechrome")

    assert label is not None
    assert label.name == "Google Chrome"
    iom.api.fetch_text.assert_not_called()


@pytest.mark.asyncio
async def test_get_label_returns_none_on_404(iom: InstallomatorClient) -> None:
    iom.api.fetch_text.side_effect = APIResponseError(
        "Not found", url="https://example.com/x.sh", status_code=404, not_found=True
    )

    label = await iom.get_label("nonexistent-app")

    assert label is None


@pytest.mark.asyncio
async def test_get_label_returns_none_on_ignored_team_id(iom: InstallomatorClient) -> None:
    # LL3KBL2M3A is in IGNORED_TEAMS (lcadvancedvpnclient)
    iom.api.fetch_text.return_value = _sample_fragment(name="LC AdvancedVPN", team_id="LL3KBL2M3A")

    label = await iom.get_label("lcadvancedvpnclient")

    assert label is None


@pytest.mark.asyncio
async def test_get_label_is_case_insensitive(iom: InstallomatorClient) -> None:
    iom.api.fetch_text.return_value = _sample_fragment()

    label_lower = await iom.get_label("googlechrome")
    label_upper = await iom.get_label("GOOGLECHROME")

    assert label_lower is label_upper  # same cached instance


@pytest.mark.asyncio
async def test_get_labels_with_explicit_names(iom: InstallomatorClient) -> None:
    iom.api.fetch_text.return_value = _sample_fragment()

    labels = await iom.get_labels({"googlechrome", "firefox"})

    assert len(labels) == 2
    assert iom.api.fetch_text.call_count == 2  # one per name


@pytest.mark.asyncio
async def test_get_labels_with_none_fetches_all(iom: InstallomatorClient) -> None:
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
async def test_get_labels_with_empty_iterable(iom: InstallomatorClient) -> None:
    labels = await iom.get_labels([])

    assert labels == []
    iom.api.fetch_text.assert_not_called()


@pytest.mark.asyncio
async def test_get_labels_skips_failed_fetches(iom: InstallomatorClient) -> None:
    """A failed fetch for one label doesn't break the batch."""

    async def fetch_text_side_effect(url: str, **kwargs) -> str:
        if "googlechrome.sh" in url:
            return _sample_fragment()
        raise APIResponseError("Not found", url=url, status_code=404, not_found=True)

    iom.api.fetch_text.side_effect = fetch_text_side_effect

    labels = await iom.get_labels(["googlechrome", "nonexistent"])

    assert len(labels) == 1
    assert labels[0].name == "Google Chrome"


def test_normalize_lowercases_strips_spaces_and_dots() -> None:
    assert InstallomatorClient._normalize("Google Chrome") == "googlechrome"
    assert InstallomatorClient._normalize("Node.js") == "nodejs"
    assert InstallomatorClient._normalize("1Password 7") == "1password7"


def test_match_directly_direct_hit(iom: InstallomatorClient) -> None:
    matched = iom._match_directly(["googlechrome"], {"googlechrome", "firefox"})
    assert matched == ["googlechrome"]


def test_match_directly_normalized_hit(iom: InstallomatorClient) -> None:
    matched = iom._match_directly(["Google Chrome"], {"googlechrome"})
    assert matched == ["googlechrome"]


def test_match_directly_no_duplicates(iom: InstallomatorClient) -> None:
    """Direct + normalized matches against the same label shouldn't double up."""
    matched = iom._match_directly(["googlechrome", "Google Chrome"], {"googlechrome"})
    assert matched == ["googlechrome"]


def test_match_directly_no_hit(iom: InstallomatorClient) -> None:
    matched = iom._match_directly(["unknown-app"], {"googlechrome"})
    assert matched == []


def test_match_fuzzy_hits_above_threshold(iom: InstallomatorClient) -> None:
    matched = iom._match_fuzzy(["google chrome"], {"googlechrome"})
    # rapidfuzz.ratio("google chrome", "googlechrome") is high enough to clear 85
    assert matched == ["googlechrome"]


def test_match_fuzzy_misses_below_threshold(iom: InstallomatorClient) -> None:
    matched = iom._match_fuzzy(["zzz-unrelated"], {"googlechrome"})
    assert matched == []


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
async def test_match_attaches_labels_to_matched_titles(iom: InstallomatorClient) -> None:
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
async def test_match_persists_unmatched_apps(iom: InstallomatorClient) -> None:
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
async def test_match_skips_ignored_title_patterns(iom: InstallomatorClient) -> None:
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
async def test_match_second_pass_finds_normalized_title(iom: InstallomatorClient) -> None:
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
async def test_match_does_nothing_on_404_from_get_app_names(iom: InstallomatorClient) -> None:
    """If get_app_names raises a 404 APIResponseError, match returns silently."""
    from src.patcher.core.exceptions import APIResponseError

    err = APIResponseError("not found", status_code=404, error="404", not_found=True)
    iom.api.get_app_names = AsyncMock(side_effect=err)

    patch_titles = [_make_patch_title("Google Chrome")]
    await iom.match(patch_titles)  # must not raise

    assert patch_titles[0].install_label == []


# Shell expression resolver tests (pyinstallomator subset).
# Uses httpx.MockTransport for HTTP fixtures — no real network, no recorded
# cassettes, just inline handlers that return canned responses.


def _mock_client(handler) -> httpx.Client:
    """Build an ``httpx.Client`` wired to the given mock handler. No real I/O."""
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestResolveLiteralValues:
    def test_plain_string_returns_as_resolved(self):
        result = resolve("121.0")
        assert result == Resolved(value="121.0")

    def test_url_returns_as_resolved(self):
        result = resolve("https://example.com/foo.dmg")
        assert isinstance(result, Resolved)
        assert result.value == "https://example.com/foo.dmg"

    def test_none_returns_unresolvable(self):
        result = resolve(None)
        assert isinstance(result, Unresolvable)


class TestResolveUrlValidation:
    """When ``is_url=True`` is passed, the resolved value is checked against
    :func:`looks_like_clean_http_url` and failures land as
    :class:`InvalidOutput` rather than :class:`Resolved`."""

    def test_clean_http_url_resolves(self):
        result = resolve("https://example.com/foo.dmg", is_url=True)
        assert result == Resolved(value="https://example.com/foo.dmg")

    def test_literal_ftp_url_is_invalid_output(self):
        result = resolve("ftp://example.com/foo.dmg", is_url=True)
        assert isinstance(result, InvalidOutput)
        assert result.raw == "ftp://example.com/foo.dmg"

    def test_literal_html_body_is_invalid_output(self):
        result = resolve("<!doctype html><html>oops</html>", is_url=True)
        assert isinstance(result, InvalidOutput)

    def test_non_url_field_skips_validation(self):
        # is_url=False is the default; ftp:// should pass through unchecked.
        result = resolve("ftp://example.com/foo.dmg")
        assert result == Resolved(value="ftp://example.com/foo.dmg")


class TestLooksLikeCleanHttpUrl:
    """
    Output sanity check for resolver values that get stored in columns the
    API serializes as ``HttpUrl``. Regression coverage for the three
    garbage classes pyinstallomator can return when a pipeline succeeds at
    the shell level but the captured output isn't a usable URL.
    """

    def test_https_url_accepted(self):
        assert looks_like_clean_http_url("https://example.com/foo.dmg") is True

    def test_http_url_accepted(self):
        assert looks_like_clean_http_url("http://example.com/foo.pkg") is True

    def test_none_rejected(self):
        assert looks_like_clean_http_url(None) is False

    def test_empty_string_rejected(self):
        assert looks_like_clean_http_url("") is False

    def test_newline_in_value_rejected(self):
        # Multi-line concat: resolver's final filter was unsupported, so the
        # full grep output (every matched URL on the page) landed in the value.
        garbage = "https://example.com/v1.dmg\nhttps://example.com/v2.dmg"
        assert looks_like_clean_http_url(garbage) is False

    def test_carriage_return_in_value_rejected(self):
        assert looks_like_clean_http_url("https://example.com/foo.dmg\r\n") is False

    def test_over_max_length_rejected(self):
        # Pydantic's HttpUrl ceiling is 2083; we cap at 2000 for headroom.
        oversized = "https://example.com/" + ("a" * 2000)
        assert looks_like_clean_http_url(oversized) is False

    def test_ftp_scheme_rejected(self):
        # A handful of Installomator labels still source from ftp://.
        # HttpUrl rejects them.
        assert looks_like_clean_http_url("ftp://cola.gmu.edu/grads/foo.tar.gz") is False

    def test_html_doctype_body_rejected(self):
        # Upstream vendor returned an error page; curl didn't see the non-2xx
        # response as an error, so the response body landed in the value.
        body = (
            '<!doctype html><html lang="en"><head><title>HTTP Status 400'
            "</title></head><body><h1>Bad Request</h1></body></html>"
        )
        assert looks_like_clean_http_url(body) is False

    def test_html_tag_body_rejected(self):
        assert looks_like_clean_http_url("<html><body>Not found</body></html>") is False

    def test_leading_whitespace_before_html_still_rejected(self):
        assert looks_like_clean_http_url("   <html>oops</html>") is False

    def test_relative_path_rejected(self):
        assert looks_like_clean_http_url("/path/to/foo.dmg") is False


class TestSplitPipeline:
    def test_simple_split(self):
        assert _split_pipeline("a | b | c") == ["a", "b", "c"]

    def test_respects_double_quotes(self):
        assert _split_pipeline('cmd "a | b" | grep x') == ['cmd "a | b"', "grep x"]

    def test_respects_single_quotes(self):
        assert _split_pipeline("cmd 'a | b' | x") == ["cmd 'a | b'", "x"]


class TestTokenize:
    def test_simple_tokenization(self):
        assert _tokenize("curl -fsIL https://example.com") == [
            "curl",
            "-fsIL",
            "https://example.com",
        ]

    def test_quoted_args_stay_together(self):
        assert _tokenize('grep -i "^location:"') == ["grep", "-i", "^location:"]


class TestExecGrep:
    def test_matches_lines(self):
        assert _exec_grep(["location"], ["location: x", "other", "Location"]) == ["location: x"]

    def test_case_insensitive(self):
        assert _exec_grep(["-i", "location"], ["LOCATION: x"]) == ["LOCATION: x"]

    def test_only_matching(self):
        out = _exec_grep(["-o", r"[0-9]+\.[0-9]+"], ["abc 121.0 def", "no version"])
        assert out == ["121.0"]

    def test_invert(self):
        assert _exec_grep(["-v", "x"], ["xyz", "abc", "xx"]) == ["abc"]


class TestExecHead:
    def test_default_10(self):
        lines = [str(i) for i in range(20)]
        assert _exec_head([], lines) == [str(i) for i in range(10)]

    def test_dash_n(self):
        assert _exec_head(["-n", "3"], ["a", "b", "c", "d"]) == ["a", "b", "c"]

    def test_dash_count(self):
        assert _exec_head(["-1"], ["a", "b", "c"]) == ["a"]


class TestExecTail:
    def test_dash_n(self):
        assert _exec_tail(["-n", "2"], ["a", "b", "c", "d"]) == ["c", "d"]

    def test_dash_count(self):
        assert _exec_tail(["-1"], ["a", "b", "c"]) == ["c"]


class TestExecCut:
    def test_single_field(self):
        assert _exec_cut(["-d", "/", "-f", "3"], ["a/b/c/d"]) == ["c"]

    def test_range_field(self):
        assert _exec_cut(["-d", "/", "-f", "2-3"], ["a/b/c/d"]) == ["b/c"]

    def test_comma_separated_fields(self):
        assert _exec_cut(["-d", "/", "-f", "1,3"], ["a/b/c/d"]) == ["a/c"]


class TestParseFieldSpec:
    def test_single(self):
        assert _parse_field_spec("3") == [3]

    def test_range(self):
        assert _parse_field_spec("2-5") == [2, 3, 4, 5]

    def test_comma(self):
        assert _parse_field_spec("1,3,5") == [1, 3, 5]


class TestExecAwk:
    def test_print_field_with_explicit_separator(self):
        assert _exec_awk(["-F", "<", "{print $4}"], ["a<b<c<d<e"]) == ["d"]

    def test_default_whitespace_split(self):
        assert _exec_awk(["{print $2}"], ["alpha beta gamma"]) == ["beta"]

    def test_out_of_range_field_yields_empty(self):
        assert _exec_awk(["{print $9}"], ["one two"]) == [""]

    def test_unsupported_program_raises(self):
        from src.patcher.core.installomator import UnsupportedOperation

        with pytest.raises(UnsupportedOperation):
            _exec_awk(['{ if ($1 == "x") print $2 }'], ["x y"])


class TestExecSed:
    def test_basic_substitute_first_occurrence(self):
        assert _exec_sed(["s/foo/bar/"], ["foo and foo"]) == ["bar and foo"]

    def test_global_flag_replaces_all(self):
        assert _exec_sed(["s/foo/bar/g"], ["foo and foo"]) == ["bar and bar"]

    def test_extended_regex_with_dash_E(self):  # noqa: N802
        assert _exec_sed(["-E", "s/[0-9]+/N/g"], ["abc123def456"]) == ["abcNdefN"]

    def test_alternate_delimiter(self):
        assert _exec_sed(["s|foo|bar|g"], ["foo/baz"]) == ["bar/baz"]

    def test_unsupported_command_raises(self):
        from src.patcher.core.installomator import UnsupportedOperation

        with pytest.raises(UnsupportedOperation):
            _exec_sed(["1,5p"], ["whatever"])


class TestExecTr:
    def test_translate_simple_sets(self):
        assert _exec_tr(["abc", "xyz"], ["aabbcc"]) == ["xxyyzz"]

    def test_delete_mode_removes_chars(self):
        assert _exec_tr(["-d", "0123456789"], ["abc123def"]) == ["abcdef"]

    def test_mismatched_set_lengths_raise(self):
        from src.patcher.core.installomator import UnsupportedOperation

        with pytest.raises(UnsupportedOperation):
            _exec_tr(["ab", "xyz"], ["whatever"])


class TestExecSort:
    def test_plain_sort(self):
        assert _exec_sort([], ["banana", "apple", "cherry"]) == ["apple", "banana", "cherry"]

    def test_reverse_sort(self):
        assert _exec_sort(["-r"], ["a", "c", "b"]) == ["c", "b", "a"]

    def test_numeric_sort(self):
        assert _exec_sort(["-n"], ["10", "2", "30"]) == ["2", "10", "30"]

    def test_unsupported_flag_raises(self):
        from src.patcher.core.installomator import UnsupportedOperation

        with pytest.raises(UnsupportedOperation):
            _exec_sort(["-k2"], ["whatever"])


class TestExecUniq:
    def test_removes_adjacent_duplicates(self):
        assert _exec_uniq([], ["a", "a", "b", "b", "a"]) == ["a", "b", "a"]

    def test_preserves_non_adjacent_duplicates(self):
        # uniq is local: non-adjacent duplicates are preserved (sort first to dedupe globally)
        assert _exec_uniq([], ["a", "b", "a"]) == ["a", "b", "a"]


class TestSubprocessFallback:
    """The opt-in fallback for pipelines containing commands native dispatch
    doesn't handle. Default off; only invoked when ``resolve`` is called with
    ``allow_subprocess_fallback=True``."""

    def test_default_off_returns_unresolvable_for_unsupported_command(self):
        # plutil is genuinely not implemented natively. Without the opt-in
        # flag, the outcome is Unresolvable.
        result = resolve("$(plutil -extract foo raw bar.plist)")
        assert isinstance(result, Unresolvable)

    def test_opt_in_runs_real_bash(self, monkeypatch):
        # Smoke test: with allow_subprocess_fallback=True, a pipeline that
        # uses real bash echo lands as Resolved. Uses /bin/bash so it works
        # on any POSIX dev box.
        result = resolve("$(echo hello)", allow_subprocess_fallback=True)
        # echo is treated as a "source" command native-dispatch doesn't
        # handle, so native dispatch raises UnsupportedOperation, then
        # fallback runs `echo hello` and captures stdout.
        assert isinstance(result, Resolved)
        assert result.value == "hello"


class TestCurlBody:
    def test_simple_get(self):
        def handler(request):
            return httpx.Response(200, text="line one\nline two\nline three")

        client = _mock_client(handler)
        result = resolve('$(curl -fs "https://example.com/")', http_client=client)
        assert isinstance(result, Resolved)
        assert result.value == "line one\nline two\nline three"

    def test_fail_silent_on_404(self):
        def handler(request):
            return httpx.Response(404)

        client = _mock_client(handler)
        result = resolve('$(curl -fs "https://example.com/")', http_client=client)
        # 404 with -fs silently drops the body; pipeline produces empty output
        # which the new shape reports as Unresolvable rather than empty Resolved.
        assert isinstance(result, Unresolvable)

    def test_grep_and_cut_pipeline(self):
        def handler(request):
            return httpx.Response(
                200,
                text=(
                    'version: "1.2.3"\n'
                    'release: "stable"\n'
                    'mirror: "https://mirror.example/v1.2.3/firefox.dmg"\n'
                ),
            )

        client = _mock_client(handler)
        result = resolve(
            '$(curl -fs "https://example.com/index.json" | grep mirror | cut -d "\\"" -f2)',
            http_client=client,
        )
        assert isinstance(result, Resolved)
        # Split on `"`: ["mirror: ", "https://mirror.example/v1.2.3/firefox.dmg", ""]
        # -f2 (1-indexed) extracts the quoted URL itself.
        assert result.value == "https://mirror.example/v1.2.3/firefox.dmg"


class TestCurlRedirectChainHeaders:
    """``curl -fsIL`` — the canonical Installomator pattern for version extraction."""

    def test_follows_chain_and_returns_each_hop_headers(self):
        """Two-hop redirect chain → 301 then 200, both header blocks returned."""
        call_count = {"n": 0}

        def handler(request):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(
                    301,
                    headers={"location": "https://cdn.example.com/firefox/121.0/Firefox-121.0.dmg"},
                )
            return httpx.Response(200, headers={"content-type": "application/octet-stream"})

        client = _mock_client(handler)
        result = resolve(
            '$(curl -fsIL "https://download.example/?product=firefox-latest" '
            "| grep -i ^location "
            '| cut -d "/" -f5)',
            http_client=client,
        )
        assert isinstance(result, Resolved)
        # Splitting Location URL on "/" (1-indexed): 1=https:, 2=, 3=cdn..., 4=firefox, 5=121.0
        assert result.value == "121.0"

    def test_terminal_response_stops_chain(self):
        def handler(request):
            return httpx.Response(200, headers={"x-final": "yes"})

        client = _mock_client(handler)
        result = resolve(
            '$(curl -fsIL "https://example.com/" | grep -i ^x-final)',
            http_client=client,
        )
        assert isinstance(result, Resolved)
        assert result.value == "x-final: yes"


class TestResolveUnsupported:
    def test_unknown_command_returns_unsupported(self):
        result = resolve("$(plutil -extract foo raw bar.plist)")
        assert isinstance(result, Unresolvable)
        assert "plutil" in result.reason

    def test_curl_without_url_returns_unsupported(self):
        result = resolve("$(curl -fs)")
        assert isinstance(result, Unresolvable)
        assert "URL" in result.reason

    def test_grep_without_pattern_returns_unsupported(self):
        def handler(request):
            return httpx.Response(200, text="anything")

        client = _mock_client(handler)
        result = resolve('$(curl -fs "https://example.com/" | grep -i)', http_client=client)
        assert isinstance(result, Unresolvable)
        assert "pattern" in result.reason.lower()

    def test_filter_command_as_source_returns_unsupported(self):
        result = resolve("$(grep foo)")
        assert isinstance(result, Unresolvable)
        assert "source command" in result.reason.lower()
