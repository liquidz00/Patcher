"""
Tests for the shell-pipeline resolver at
:mod:`patcher_api.installomator.resolver`.

Uses ``httpx.MockTransport`` for HTTP fixtures — no real network, no recorded
cassettes, just inline handlers that return canned responses.

Historically lived alongside ``tests/test_installomator.py`` when the resolver
was part of the ``patcher`` package. It moved here when the resolver moved
to the API workspace (its only real consumer).
"""

from __future__ import annotations

import httpx
import pytest
from patcher_api.installomator.resolver import (
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
        from patcher_api.installomator.resolver import UnsupportedOperation

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
        from patcher_api.installomator.resolver import UnsupportedOperation

        with pytest.raises(UnsupportedOperation):
            _exec_sed(["1,5p"], ["whatever"])


class TestExecTr:
    def test_translate_simple_sets(self):
        assert _exec_tr(["abc", "xyz"], ["aabbcc"]) == ["xxyyzz"]

    def test_delete_mode_removes_chars(self):
        assert _exec_tr(["-d", "0123456789"], ["abc123def"]) == ["abcdef"]

    def test_mismatched_set_lengths_raise(self):
        from patcher_api.installomator.resolver import UnsupportedOperation

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
        from patcher_api.installomator.resolver import UnsupportedOperation

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

    def test_nonzero_exit_returns_unresolvable_with_truncated_stderr(self):
        """Pipeline exits non-zero -> Unresolvable carrying a truncated stderr.

        The fallback caps stderr at 200 chars in the reason string so a
        chatty failure can't blow up logs. Exercises the actual subprocess
        path with a real bash command that writes a long stderr and exits 1.
        """
        long_msg = "x" * 500
        result = resolve(
            f'$(bash -c "echo {long_msg} >&2; exit 1")',
            allow_subprocess_fallback=True,
        )
        assert isinstance(result, Unresolvable)
        # The truncation happens inside _subprocess_fallback (200-char cap).
        # `Unresolvable.reason` contains the subprocess error text, which the
        # outer dispatcher wraps but preserves verbatim.
        assert "exited 1" in result.reason
        # Truncation cap is 200 chars; full 500-x string should never appear.
        assert "x" * 500 not in result.reason

    def test_subprocess_timeout_returns_unresolvable(self, monkeypatch):
        """A pipeline that exceeds the 30s timeout returns Unresolvable.

        Mocked rather than waiting 30s with a `sleep` pipeline. We patch
        `subprocess.run` to raise TimeoutExpired and assert the failure
        path translates it into Unresolvable.
        """
        import subprocess

        from patcher_api.installomator import resolver as installomator_resolver

        def fake_run(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="bash", timeout=30.0)

        monkeypatch.setattr(installomator_resolver.subprocess, "run", fake_run)
        result = resolve("$(plutil -extract foo raw bar.plist)", allow_subprocess_fallback=True)
        assert isinstance(result, Unresolvable)
        assert "timed out" in result.reason

    def test_subprocess_os_error_returns_unresolvable(self, monkeypatch):
        """OSError starting bash -> Unresolvable, not a crash.

        Defends the path where the host has no /bin/bash (rare on POSIX,
        but a real failure mode on stripped-down containers). Mocked because
        we can't actually remove /bin/bash from a dev box for a test.
        """
        from patcher_api.installomator import resolver as installomator_resolver

        def fake_run(*_args, **_kwargs):
            raise OSError("[Errno 2] No such file or directory: '/bin/bash'")

        monkeypatch.setattr(installomator_resolver.subprocess, "run", fake_run)
        result = resolve("$(plutil -extract foo raw bar.plist)", allow_subprocess_fallback=True)
        assert isinstance(result, Unresolvable)
        assert "could not start bash" in result.reason


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
