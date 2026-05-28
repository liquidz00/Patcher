"""
Tests for Installomator label ingestion.

Uses inline fixture fragments rather than hitting GitHub — fast, deterministic,
offline. The fragments are real Installomator label syntax (verified against
the upstream repo); changes here should track upstream label format changes.
"""

import httpx
import pytest
from patcher_api.installomator.ingest import (
    IGNORED_TEAMS,
    FetchPlan,
    _fetch_upstream_tree,
    fetch_installomator_labels,
    ingest_installomator_labels,
    parse_fragment,
)
from patcher_api.models.installomator import InstallomatorLabel
from sqlalchemy import select

FIREFOX_FRAGMENT = """firefoxpkg)
    name="Firefox"
    type="pkg"
    packageID="org.mozilla.firefox"
    downloadURL="https://download.mozilla.org/?product=firefox-pkg-latest-ssl&os=osx&lang=en-US"
    appNewVersion=$(curl -fsIL "https://download.mozilla.org/?product=firefox-pkg-latest-ssl&os=osx" | grep -i ^location | cut -d "/" -f7)
    expectedTeamID="43AQ936H96"
    blockingProcesses=( firefox )
    ;;
"""

GOOGLECHROME_FRAGMENT = """googlechromepkg)
    name="Google Chrome"
    type="pkg"
    packageID="com.google.Chrome"
    downloadURL="https://dl.google.com/chrome/mac/stable/GGRO/googlechrome.pkg"
    expectedTeamID="EQHXZ8M8AV"
    updateTool="/Library/Google/GoogleSoftwareUpdate/GoogleSoftwareUpdate.bundle/Contents/Resources/GoogleSoftwareUpdateAgent.app/Contents/MacOS/GoogleSoftwareUpdateAgent"
    blockingProcesses=( "Google Chrome" )
    ;;
"""

IGNORED_TEAM_FRAGMENT = """somelabel)
    name="Ignored"
    type="dmg"
    downloadURL="https://example.com/foo.dmg"
    expectedTeamID="LL3KBL2M3A"
    ;;
"""

EMPTY_FRAGMENT = ""

# Regression fixture for the toonboomstoryboardpro2025 bug — appNewVersion
# declared with bash array syntax, which the parser returns as a Python list.
# The scalar TEXT column can't bind a list directly.
ARRAY_VERSION_FRAGMENT = """toonboomthing)
    name="Storyboard Pro 25"
    type="dmg"
    downloadURL="https://fileshare.toonboom.com/wl/?id=...&path=..."
    appNewVersion=(${version}.${build})
    expectedTeamID="U5LPYJSPQ3"
    ;;
"""

# Regression fixture for resolver-output-validation. The label has a
# shell-expression downloadURL so resolve() gets called on it; per-test
# monkeypatching of resolve() then injects the various garbage classes the
# real Installomator pipelines produce when an unsupported filter drops
# off the chain (HTML bodies, multi-line concats, ftp:// schemes).
SHELL_DOWNLOAD_FRAGMENT = """garbagelabel)
    name="GarbageLabel"
    type="dmg"
    downloadURL=$(curl -fsL https://vendor.example.com/list | grep -E 'https://.*\\.dmg')
    expectedTeamID="ABC123XYZ4"
    ;;
"""

# Literal-but-bogus URL fixture for the resolution-off path. Confirms the
# validator gate runs even when PATCHER_API_RESOLVE_INGEST is unset.
LITERAL_FTP_FRAGMENT = """ftplabel)
    name="FtpLabel"
    type="dmg"
    downloadURL="ftp://example.com/foo.dmg"
    expectedTeamID="ABC123XYZ4"
    ;;
"""


def test_parse_fragment_extracts_literal_assignments():
    parsed = parse_fragment(FIREFOX_FRAGMENT)

    assert parsed["name"] == "Firefox"
    assert parsed["type"] == "pkg"
    assert parsed["packageID"] == "org.mozilla.firefox"
    assert parsed["expectedTeamID"] == "43AQ936H96"


def test_parse_fragment_preserves_shell_expressions_as_raw_strings():
    """``appNewVersion=$(...)`` stays as the literal expression — never evaluated."""
    parsed = parse_fragment(FIREFOX_FRAGMENT)

    assert parsed["appNewVersion"].startswith("$(curl")
    assert "$(curl -fsIL" in parsed["appNewVersion"]


def test_parse_fragment_handles_bash_arrays():
    parsed = parse_fragment(FIREFOX_FRAGMENT)

    assert parsed["blockingProcesses"] == ["firefox"]


def test_parse_fragment_handles_quoted_array_entries():
    """Arrays with spaces inside quoted entries should be parsed as single elements."""
    parsed = parse_fragment(GOOGLECHROME_FRAGMENT)

    assert parsed["blockingProcesses"] == ["Google Chrome"]


def test_parse_fragment_returns_empty_dict_for_empty_input():
    assert parse_fragment(EMPTY_FRAGMENT) == {}


# --- issue #65 regression fixtures (derived from real upstream labels) ---

# beyondcomparepro: nested ')' inside $( ) and a space inside ${ } — the old
# non-greedy regex truncated rawVersion at "latestversion)" and appNewVersion
# at the space in "// build /.".
NESTED_PAREN_FRAGMENT = """beyondcomparepro)
    name="Beyond Compare"
    type="zip"
    rawVersion=$(echo "${updateFeed}" | xpath 'string(/Update/@latestversion)' 2>/dev/null)
    appNewVersion=${rawVersion// build /.}
    downloadURL=$(echo "${updateFeed}" | xpath 'string(/Update/@download)' 2>/dev/null)
    expectedTeamID="BS29TEJF86"
    ;;
"""

# Resolve-then-transform: appNewVersion assigned twice. The old parser kept
# only the last (the transform), discarding the resolving curl.
CHAIN_FRAGMENT = """chainlabel)
    name="Chain"
    type="dmg"
    appNewVersion=$(curl -fs https://example.com/v | jq -r '.version')
    appNewVersion=${appNewVersion%.0}
    expectedTeamID="ABC123XYZ4"
    ;;
"""

# Arch-conditional: archiveName assigned per-arch. Installomator checks arm64
# first by convention, so first-assignment wins gives the arm64 variant.
ARCH_FRAGMENT = """archlabel)
    name="Arch"
    type="dmg"
    if [[ $(arch) == "arm64" ]]; then
        archiveName="App-arm64.dmg"
    elif [[ $(arch) == "i386" ]]; then
        archiveName="App-x64.dmg"
    fi
    expectedTeamID="ABC123XYZ4"
    ;;
"""

# Multi-line command substitution (camtasia-style): $( on one line, body and
# closing ) on later lines.
MULTILINE_FRAGMENT = """multiline)
    name="Multi"
    type="dmg"
    appNewVersion=$(
        curl -fs "https://example.com/feed" | grep -Eo "[0-9.]+" | head -1
    )
    expectedTeamID="ABC123XYZ4"
    ;;
"""

# Array whose element is itself a command substitution (adobereaderdc-style).
ARRAY_CMDSUB_FRAGMENT = """arraycmd)
    name="ArrayCmd"
    type="dmg"
    versions=( $(curl -s "https://example.com/list" | grep -Eo "[0-9.]+" | head -n 5) )
    expectedTeamID="ABC123XYZ4"
    ;;
"""

# Command substitution inside double quotes, with its own nested "..." strings
# (adium-style). A flat quote tracker closes the outer quote at the first inner
# double quote; the context stack keeps the value whole.
NESTED_QUOTE_FRAGMENT = """nestedq)
    name="Nested"
    type="dmg"
    appNewVersion="$(curl -sL "https://example.im" | sed -r 's/.*href="([^"]+).*/\\1/g')"
    expectedTeamID="ABC123XYZ4"
    ;;
"""

# A full-line comment containing an apostrophe ("it's"). The logical-line
# joiner must not treat that lone quote as an open span and swallow the
# assignments that follow (adobeconnect-style).
COMMENT_APOSTROPHE_FRAGMENT = """commentlabel)
    # Looks like it's an installer, probably won't work
    name="CommentApp"
    type="dmg"
    downloadURL="https://example.com/app.dmg"
    expectedTeamID="ABC123XYZ4"
    ;;
"""


def test_parse_fragment_does_not_truncate_nested_parens():
    """A ``)`` inside ``$( )`` or a space inside ``${ }`` no longer truncates."""
    parsed = parse_fragment(NESTED_PAREN_FRAGMENT)

    # full pipeline captured, including the trailing 2>/dev/null)
    assert parsed["rawVersion"].endswith("2>/dev/null)")
    assert "xpath 'string(/Update/@latestversion)'" in parsed["rawVersion"]
    # the space inside ${ } survives instead of cutting at "${rawVersion//"
    assert parsed["appNewVersion"] == "${rawVersion// build /.}"
    assert parsed["downloadURL"].endswith("2>/dev/null)")


def test_parse_fragment_preserves_multi_assignment_chain():
    """A key assigned twice keeps both, in order; the resolve step isn't lost."""
    parsed = parse_fragment(CHAIN_FRAGMENT)

    assert isinstance(parsed["appNewVersion"], list)
    assert len(parsed["appNewVersion"]) == 2
    # first assignment is the resolving curl (the scalar column takes this one)
    assert parsed["appNewVersion"][0].startswith("$(curl")
    assert parsed["appNewVersion"][1] == "${appNewVersion%.0}"


def test_parse_fragment_arch_conditional_first_assignment_is_arm64():
    parsed = parse_fragment(ARCH_FRAGMENT)

    assert parsed["archiveName"] == ["App-arm64.dmg", "App-x64.dmg"]


def test_parse_fragment_reads_multiline_command_substitution():
    parsed = parse_fragment(MULTILINE_FRAGMENT)

    value = parsed["appNewVersion"]
    assert value.startswith("$(")
    assert value.rstrip().endswith(")")
    assert "head -1" in value


def test_parse_fragment_array_element_with_command_sub_stays_whole():
    parsed = parse_fragment(ARRAY_CMDSUB_FRAGMENT)

    assert isinstance(parsed["versions"], list)
    assert len(parsed["versions"]) == 1
    assert parsed["versions"][0].startswith("$(curl")
    assert parsed["versions"][0].endswith(")")


def test_parse_fragment_handles_command_sub_inside_double_quotes():
    parsed = parse_fragment(NESTED_QUOTE_FRAGMENT)

    value = parsed["appNewVersion"]
    # surrounding quotes stripped, inner $( ) intact with its nested quotes
    assert value.startswith("$(curl -sL")
    assert '"https://example.im"' in value
    assert value.endswith(")")


def test_parse_fragment_comment_apostrophe_does_not_swallow_assignments():
    parsed = parse_fragment(COMMENT_APOSTROPHE_FRAGMENT)

    assert parsed["name"] == "CommentApp"
    assert parsed["type"] == "dmg"
    assert parsed["downloadURL"] == "https://example.com/app.dmg"
    assert parsed["expectedTeamID"] == "ABC123XYZ4"


def test_parse_fragment_single_assignment_stays_scalar():
    """Regression guard: a key assigned once is a string, not a one-item list."""
    parsed = parse_fragment(CHAIN_FRAGMENT)

    assert isinstance(parsed["name"], str)
    assert parsed["name"] == "Chain"


@pytest.mark.asyncio
async def test_ingest_stores_realistic_label(test_session, monkeypatch):
    # Enable the opt-in resolver path for this test, AND mock the underlying
    # resolve() so it stays offline + deterministic. The Firefox label's
    # appNewVersion is a curl pipeline; we don't want the test suite hitting
    # download.mozilla.org. Stub returns a fixed version for the curl
    # expression, passes literals through unchanged.
    from patcher_api.installomator.resolver import Resolved, Unresolvable

    monkeypatch.setattr("patcher_api.installomator.ingest._RESOLVE_ON_INGEST", True)

    def fake_resolve(
        expression,
        *,
        http_client=None,
        is_url=False,
        is_version=False,
        allow_subprocess_fallback=False,
        context=None,
    ):
        if expression is None:
            return Unresolvable(reason="none")
        if expression.startswith("$("):
            return Resolved(value="121.0")
        return Resolved(value=expression)

    monkeypatch.setattr("patcher_api.installomator.ingest.resolve", fake_resolve)

    ingested, skipped, failed = await ingest_installomator_labels(
        test_session, {"firefoxpkg": FIREFOX_FRAGMENT}
    )

    assert ingested == 1
    assert skipped == 0

    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "firefoxpkg")
    )
    assert label is not None
    assert label.display_name == "Firefox"
    assert label.install_type == "pkg"
    assert label.package_id == "org.mozilla.firefox"
    assert label.expected_team_id == "43AQ936H96"
    # Resolver was wired through ingest: the curl shell expression became a
    # real version string. The raw fragment is still preserved untouched.
    assert label.app_new_version == "121.0"
    assert label.raw["appNewVersion"].startswith("$(curl")
    assert label.raw["blockingProcesses"] == ["firefox"]
    # The verbatim .sh body is persisted intact, not reconstructed from raw.
    assert label.fragment == FIREFOX_FRAGMENT


@pytest.mark.asyncio
async def test_ingest_skips_ignored_team_ids(test_session):
    """Labels whose expectedTeamID is in IGNORED_TEAMS are filtered out."""
    assert "LL3KBL2M3A" in IGNORED_TEAMS

    ingested, skipped, failed = await ingest_installomator_labels(
        test_session, {"somelabel": IGNORED_TEAM_FRAGMENT}
    )

    assert ingested == 0
    assert skipped == 1


@pytest.mark.asyncio
async def test_ingest_skips_empty_fragments(test_session):
    ingested, skipped, failed = await ingest_installomator_labels(
        test_session, {"emptylabel": EMPTY_FRAGMENT}
    )

    assert ingested == 0
    assert skipped == 1


@pytest.mark.asyncio
async def test_ingest_upserts_on_re_run(test_session):
    """Re-running ingestion updates the existing row rather than duplicating."""
    v1 = FIREFOX_FRAGMENT
    v2 = FIREFOX_FRAGMENT.replace("Firefox", "Firefox (updated)")

    await ingest_installomator_labels(test_session, {"firefoxpkg": v1})
    await ingest_installomator_labels(test_session, {"firefoxpkg": v2})

    labels = (await test_session.scalars(select(InstallomatorLabel))).all()
    assert len(labels) == 1
    assert labels[0].display_name == "Firefox (updated)"


@pytest.mark.asyncio
async def test_ingest_handles_array_valued_scalar_column(test_session):
    """Regression: some labels declare ``appNewVersion=(${version}.${build})`` —
    bash array syntax that the parser returns as a Python list. The scalar
    TEXT column needs a string; we surface the list's first element. Full
    list still preserved in ``raw``.

    Note: the first element here is ``${version}.${build}`` — a shell
    substitution that pyinstallomator can't resolve without variable scope.
    The ingest nulls the projected column rather than storing the raw fragment;
    the full array stays in ``raw`` for callers that need it.
    """
    ingested, skipped, failed = await ingest_installomator_labels(
        test_session, {"toonboomthing": ARRAY_VERSION_FRAGMENT}
    )

    assert ingested == 1
    assert skipped == 0

    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "toonboomthing")
    )
    # Shell substitution can't be resolved → projected column nulls out
    assert label.app_new_version is None
    # Full array structure preserved in raw for callers that need it
    assert label.raw["appNewVersion"] == ["${version}.${build}"]


@pytest.mark.asyncio
async def test_ingest_handles_mixed_batch(test_session):
    """One bad label doesn't poison the rest of the batch."""
    ingested, skipped, failed = await ingest_installomator_labels(
        test_session,
        {
            "firefoxpkg": FIREFOX_FRAGMENT,
            "googlechromepkg": GOOGLECHROME_FRAGMENT,
            "somelabel": IGNORED_TEAM_FRAGMENT,
            "emptylabel": EMPTY_FRAGMENT,
        },
    )

    assert ingested == 2
    assert skipped == 2
    assert failed == 0
    labels = (await test_session.scalars(select(InstallomatorLabel))).all()
    assert {label.name for label in labels} == {"firefoxpkg", "googlechromepkg"}


@pytest.mark.asyncio
async def test_ingest_nulls_html_body_returned_by_resolver(test_session, monkeypatch):
    """
    Resolver returned an HTML error page (upstream vendor served a 400/404,
    curl didn't treat it as an error). The validator must catch this so the
    HTML body never lands in the ``download_url`` column.
    """
    from patcher_api.installomator.resolver import (
        InvalidOutput,
        Resolved,
        looks_like_clean_http_url,
    )

    monkeypatch.setattr("patcher_api.installomator.ingest._RESOLVE_ON_INGEST", True)

    html_body = (
        '<!doctype html><html lang="en"><head><title>HTTP Status 400'
        "</title></head><body><h1>Bad Request</h1></body></html>"
    )

    def fake_resolve(
        expression,
        *,
        http_client=None,
        is_url=False,
        is_version=False,
        allow_subprocess_fallback=False,
        context=None,
    ):
        value = html_body if expression and expression.startswith("$(") else expression
        if is_url and value is not None and not looks_like_clean_http_url(value):
            return InvalidOutput(raw=value, reason="bad url")
        return Resolved(value=value)

    monkeypatch.setattr("patcher_api.installomator.ingest.resolve", fake_resolve)

    ingested, skipped, failed = await ingest_installomator_labels(
        test_session, {"garbagelabel": SHELL_DOWNLOAD_FRAGMENT}
    )

    assert ingested == 1
    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "garbagelabel")
    )
    assert label.download_url is None


@pytest.mark.asyncio
async def test_ingest_nulls_multi_line_concat_returned_by_resolver(test_session, monkeypatch):
    """
    Resolver returned a newline-joined list of URLs (the pipeline's final
    ``head -n1`` or ``awk`` was unsupported, so the full grep output came
    back). Validator must catch the embedded newline.
    """
    from patcher_api.installomator.resolver import (
        InvalidOutput,
        Resolved,
        looks_like_clean_http_url,
    )

    monkeypatch.setattr("patcher_api.installomator.ingest._RESOLVE_ON_INGEST", True)

    multi_line = (
        "https://example.com/app-2.6.5.dmg\n"
        "https://example.com/app-2.6.4.dmg\n"
        "https://example.com/app-2.6.3.dmg"
    )

    def fake_resolve(
        expression,
        *,
        http_client=None,
        is_url=False,
        is_version=False,
        allow_subprocess_fallback=False,
        context=None,
    ):
        value = multi_line if expression and expression.startswith("$(") else expression
        if is_url and value is not None and not looks_like_clean_http_url(value):
            return InvalidOutput(raw=value, reason="bad url")
        return Resolved(value=value)

    monkeypatch.setattr("patcher_api.installomator.ingest.resolve", fake_resolve)

    ingested, skipped, failed = await ingest_installomator_labels(
        test_session, {"garbagelabel": SHELL_DOWNLOAD_FRAGMENT}
    )

    assert ingested == 1
    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "garbagelabel")
    )
    assert label.download_url is None


@pytest.mark.asyncio
async def test_ingest_nulls_ftp_url_returned_by_resolver(test_session, monkeypatch):
    """
    Resolver returned a syntactically valid but non-http(s) URL. Pydantic's
    ``HttpUrl`` would reject it on the response side, so the validator
    nulls it here at ingest.
    """
    from patcher_api.installomator.resolver import (
        InvalidOutput,
        Resolved,
        looks_like_clean_http_url,
    )

    monkeypatch.setattr("patcher_api.installomator.ingest._RESOLVE_ON_INGEST", True)

    ftp_url = "ftp://cola.gmu.edu/grads/foo.tar.gz"

    def fake_resolve(
        expression,
        *,
        http_client=None,
        is_url=False,
        is_version=False,
        allow_subprocess_fallback=False,
        context=None,
    ):
        value = ftp_url if expression and expression.startswith("$(") else expression
        if is_url and value is not None and not looks_like_clean_http_url(value):
            return InvalidOutput(raw=value, reason="bad url")
        return Resolved(value=value)

    monkeypatch.setattr("patcher_api.installomator.ingest.resolve", fake_resolve)

    ingested, skipped, failed = await ingest_installomator_labels(
        test_session, {"garbagelabel": SHELL_DOWNLOAD_FRAGMENT}
    )

    assert ingested == 1
    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "garbagelabel")
    )
    assert label.download_url is None


@pytest.mark.asyncio
async def test_ingest_nulls_garbage_app_new_version_returned_by_resolver(test_session, monkeypatch):
    """
    Resolver succeeded at the shell level but the appNewVersion pipeline
    captured an HTML page (final filter unsupported). The version validator
    must null it rather than store a 28KB blob as a version.
    """
    from patcher_api.installomator.resolver import (
        InvalidOutput,
        Resolved,
        looks_like_clean_version,
    )

    monkeypatch.setattr("patcher_api.installomator.ingest._RESOLVE_ON_INGEST", True)

    html_body = '<meta name="viewport" content="width=device-width, initial-scale=1.0">'

    def fake_resolve(
        expression,
        *,
        http_client=None,
        is_url=False,
        is_version=False,
        allow_subprocess_fallback=False,
        context=None,
    ):
        value = html_body if expression and expression.startswith("$(") else expression
        if is_version and value is not None and not looks_like_clean_version(value):
            return InvalidOutput(raw=value, reason="bad version")
        return Resolved(value=value)

    monkeypatch.setattr("patcher_api.installomator.ingest.resolve", fake_resolve)

    ingested, skipped, failed = await ingest_installomator_labels(
        test_session, {"garbagelabel": _DYNAMIC_VERSION_FRAGMENT}
    )

    assert ingested == 1
    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "garbagelabel")
    )
    assert label.app_new_version is None


@pytest.mark.asyncio
async def test_ingest_nulls_literal_ftp_url_with_resolution_off(test_session):
    """
    The validator runs on the resolution-off path too: a literal ``ftp://``
    label download_url should be nulled even when the resolver was never
    consulted. Defends against the rare label that has a non-http literal.
    """
    ingested, skipped, failed = await ingest_installomator_labels(
        test_session, {"ftplabel": LITERAL_FTP_FRAGMENT}
    )

    assert ingested == 1
    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "ftplabel")
    )
    assert label.download_url is None
    # Raw fragment is still preserved for any caller that needs the original.
    assert label.raw["downloadURL"] == "ftp://example.com/foo.dmg"


@pytest.mark.asyncio
async def test_ingest_row_failure_does_not_poison_remaining_batch(test_session, monkeypatch):
    """If a single row INSERT raises, surrounding rows still commit successfully."""
    from patcher_api.installomator import ingest as ingest_module

    real_scalar = ingest_module._scalar_for_column
    call_count = {"n": 0}

    def flaky_scalar(value):
        """Raise on the second invocation to simulate an unexpected mid-batch error."""
        call_count["n"] += 1
        if call_count["n"] == 8:  # second label's first column-coerce call
            raise RuntimeError("simulated row failure")
        return real_scalar(value)

    monkeypatch.setattr(ingest_module, "_scalar_for_column", flaky_scalar)

    ingested, skipped, failed = await ingest_installomator_labels(
        test_session,
        {"firefoxpkg": FIREFOX_FRAGMENT, "googlechromepkg": GOOGLECHROME_FRAGMENT},
    )

    # Exactly one row survives the batch; the other fails on the flaky
    # scalar. Which one fails depends on call ordering across the parallel
    # resolve phase and the serial persist phase, so the test asserts the
    # batch-survival invariant rather than a specific victim.
    assert ingested == 1
    assert failed == 1
    labels = (await test_session.scalars(select(InstallomatorLabel))).all()
    assert len(labels) == 1
    assert labels[0].name in {"firefoxpkg", "googlechromepkg"}


# SHA-gating: tree discovery, gating logic, force, deletion, blob_sha persistence.

_TREE_RESPONSE_TWO_LABELS = {
    "sha": "deadbeef",
    "url": "https://api.github.com/...",
    "truncated": False,
    "tree": [
        {
            "mode": "100644",
            "path": "fragments/labels/firefoxpkg.sh",
            "sha": "sha-firefox-v1",
            "size": 400,
            "type": "blob",
            "url": "https://api.github.com/...",
        },
        {
            "mode": "100644",
            "path": "fragments/labels/googlechromepkg.sh",
            "sha": "sha-chrome-v1",
            "size": 350,
            "type": "blob",
            "url": "https://api.github.com/...",
        },
        # Non-fragment entries that must be filtered out.
        {
            "mode": "040000",
            "path": "fragments/labels",
            "sha": "tree-sha",
            "type": "tree",
            "url": "https://api.github.com/...",
        },
        {
            "mode": "100644",
            "path": "README.md",
            "sha": "readme-sha",
            "size": 1000,
            "type": "blob",
            "url": "https://api.github.com/...",
        },
        {
            "mode": "100644",
            "path": "fragments/labels/NOT_A_FRAGMENT.md",
            "sha": "md-sha",
            "size": 200,
            "type": "blob",
            "url": "https://api.github.com/...",
        },
    ],
}


def _mock_client(handler) -> httpx.AsyncClient:
    """Build an AsyncClient routed through a MockTransport handler."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _make_handler(
    *,
    tree_payload: dict,
    fragment_payloads: dict[str, str] | None = None,
) -> "callable":
    """Build a MockTransport handler that routes tree + fragment requests."""
    fragments = fragment_payloads or {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "api.github.com" in request.url.host and "/git/trees/" in request.url.path:
            return httpx.Response(200, json=tree_payload)
        if "raw.githubusercontent.com" in request.url.host:
            name = request.url.path.rsplit("/", 1)[-1].removesuffix(".sh")
            if name in fragments:
                return httpx.Response(200, text=fragments[name])
            return httpx.Response(404, text="not found")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    return handler


@pytest.mark.asyncio
async def test_fetch_upstream_tree_filters_to_fragment_blobs():
    """Tree response carries every repo file; we only want labels/*.sh blobs."""
    handler = _make_handler(tree_payload=_TREE_RESPONSE_TWO_LABELS)
    client = _mock_client(handler)
    try:
        upstream = await _fetch_upstream_tree(client=client)
    finally:
        await client.aclose()

    assert upstream == {
        "firefoxpkg": "sha-firefox-v1",
        "googlechromepkg": "sha-chrome-v1",
    }


@pytest.mark.asyncio
async def test_fetch_upstream_tree_authenticates_with_token(monkeypatch):
    """The git/trees call (api.github.com, 60/hr unauth) uses the token when set."""
    monkeypatch.setenv("PATCHER_API_GITHUB_TOKEN", "ghp_testtoken")
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_TREE_RESPONSE_TWO_LABELS)

    client = _mock_client(handler)
    try:
        await _fetch_upstream_tree(client=client)
    finally:
        await client.aclose()

    assert seen["auth"] == "Bearer ghp_testtoken"


@pytest.mark.asyncio
async def test_fetch_upstream_tree_no_auth_header_without_token(monkeypatch):
    monkeypatch.delenv("PATCHER_API_GITHUB_TOKEN", raising=False)
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_TREE_RESPONSE_TWO_LABELS)

    client = _mock_client(handler)
    try:
        await _fetch_upstream_tree(client=client)
    finally:
        await client.aclose()

    assert seen["auth"] is None


@pytest.mark.asyncio
async def test_fetch_upstream_tree_warns_on_truncated_response(caplog):
    payload = dict(_TREE_RESPONSE_TWO_LABELS, truncated=True)
    handler = _make_handler(tree_payload=payload)
    client = _mock_client(handler)
    try:
        with caplog.at_level("WARNING"):
            await _fetch_upstream_tree(client=client)
    finally:
        await client.aclose()

    assert any("truncated" in rec.message.lower() for rec in caplog.records)


@pytest.mark.asyncio
async def test_fetch_installomator_labels_no_existing_fetches_everything():
    """With no stored SHAs, every upstream label counts as new."""
    handler = _make_handler(
        tree_payload=_TREE_RESPONSE_TWO_LABELS,
        fragment_payloads={
            "firefoxpkg": FIREFOX_FRAGMENT,
            "googlechromepkg": GOOGLECHROME_FRAGMENT,
        },
    )
    client = _mock_client(handler)
    try:
        plan = await fetch_installomator_labels(client=client)
    finally:
        await client.aclose()

    assert isinstance(plan, FetchPlan)
    assert set(plan.name_to_content) == {"firefoxpkg", "googlechromepkg"}
    assert plan.name_to_blob_sha == {
        "firefoxpkg": "sha-firefox-v1",
        "googlechromepkg": "sha-chrome-v1",
    }
    assert plan.removed == frozenset()
    assert plan.unchanged == 0
    assert plan.missing == 0
    assert plan.errored == 0


@pytest.mark.asyncio
async def test_fetch_installomator_labels_skips_unchanged():
    """Stored SHA matches upstream → label not re-fetched, counted as unchanged."""
    fragment_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "api.github.com" in request.url.host:
            return httpx.Response(200, json=_TREE_RESPONSE_TWO_LABELS)
        if "raw.githubusercontent.com" in request.url.host:
            name = request.url.path.rsplit("/", 1)[-1].removesuffix(".sh")
            fragment_requests.append(name)
            return httpx.Response(200, text=FIREFOX_FRAGMENT if name == "firefoxpkg" else "")
        raise AssertionError(f"unexpected request: {request.url}")

    client = _mock_client(handler)
    try:
        plan = await fetch_installomator_labels(
            client=client,
            existing_blob_shas={
                "googlechromepkg": "sha-chrome-v1",  # matches upstream
            },
        )
    finally:
        await client.aclose()

    assert set(plan.name_to_content) == {"firefoxpkg"}  # chrome skipped
    assert fragment_requests == ["firefoxpkg"]  # no chrome fetch
    assert plan.unchanged == 1


@pytest.mark.asyncio
async def test_fetch_installomator_labels_reports_removed():
    """Labels in DB but not upstream are returned for caller deletion."""
    handler = _make_handler(
        tree_payload=_TREE_RESPONSE_TWO_LABELS,
        fragment_payloads={
            "firefoxpkg": FIREFOX_FRAGMENT,
            "googlechromepkg": GOOGLECHROME_FRAGMENT,
        },
    )
    client = _mock_client(handler)
    try:
        plan = await fetch_installomator_labels(
            client=client,
            existing_blob_shas={
                "firefoxpkg": "sha-firefox-v0",  # changed
                "googlechromepkg": "sha-chrome-v1",  # unchanged
                "oldlabel": "sha-old",  # not upstream → remove
            },
        )
    finally:
        await client.aclose()

    assert plan.removed == frozenset({"oldlabel"})


@pytest.mark.asyncio
async def test_fetch_installomator_labels_all_unchanged_returns_empty_content():
    handler = _make_handler(
        tree_payload=_TREE_RESPONSE_TWO_LABELS,
        fragment_payloads={
            "firefoxpkg": FIREFOX_FRAGMENT,
            "googlechromepkg": GOOGLECHROME_FRAGMENT,
        },
    )
    client = _mock_client(handler)
    try:
        plan = await fetch_installomator_labels(
            client=client,
            existing_blob_shas={
                "firefoxpkg": "sha-firefox-v1",
                "googlechromepkg": "sha-chrome-v1",
            },
        )
    finally:
        await client.aclose()

    assert plan.name_to_content == {}
    assert plan.unchanged == 2
    # Upstream SHA map is still returned in full so callers can refresh
    # the stored SHA even when content didn't change.
    assert plan.name_to_blob_sha == {
        "firefoxpkg": "sha-firefox-v1",
        "googlechromepkg": "sha-chrome-v1",
    }


@pytest.mark.asyncio
async def test_fetch_installomator_labels_force_bypasses_gating():
    """force=True re-fetches even when stored SHAs match upstream."""
    handler = _make_handler(
        tree_payload=_TREE_RESPONSE_TWO_LABELS,
        fragment_payloads={
            "firefoxpkg": FIREFOX_FRAGMENT,
            "googlechromepkg": GOOGLECHROME_FRAGMENT,
        },
    )
    client = _mock_client(handler)
    try:
        plan = await fetch_installomator_labels(
            client=client,
            existing_blob_shas={
                "firefoxpkg": "sha-firefox-v1",
                "googlechromepkg": "sha-chrome-v1",
            },
            force=True,
        )
    finally:
        await client.aclose()

    assert set(plan.name_to_content) == {"firefoxpkg", "googlechromepkg"}
    assert plan.unchanged == 0


@pytest.mark.asyncio
async def test_ingest_persists_blob_sha_when_provided(test_session):
    """blob_sha lands in the column when name_to_blob_sha is passed through."""
    await ingest_installomator_labels(
        test_session,
        {"firefoxpkg": FIREFOX_FRAGMENT},
        name_to_blob_sha={"firefoxpkg": "sha-firefox-v1"},
    )

    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "firefoxpkg")
    )
    assert label.blob_sha == "sha-firefox-v1"


@pytest.mark.asyncio
async def test_ingest_leaves_blob_sha_null_when_map_absent(test_session):
    """Backward-compat: existing callers that don't pass name_to_blob_sha still work."""
    await ingest_installomator_labels(test_session, {"firefoxpkg": FIREFOX_FRAGMENT})

    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "firefoxpkg")
    )
    assert label.blob_sha is None


@pytest.mark.asyncio
async def test_ingest_updates_blob_sha_on_upsert(test_session):
    """Re-ingesting the same label with a new SHA updates the column."""
    await ingest_installomator_labels(
        test_session,
        {"firefoxpkg": FIREFOX_FRAGMENT},
        name_to_blob_sha={"firefoxpkg": "sha-firefox-v1"},
    )
    await ingest_installomator_labels(
        test_session,
        {"firefoxpkg": FIREFOX_FRAGMENT},
        name_to_blob_sha={"firefoxpkg": "sha-firefox-v2"},
    )

    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "firefoxpkg")
    )
    assert label.blob_sha == "sha-firefox-v2"


_DYNAMIC_VERSION_FRAGMENT = """freshtest)
    name="FreshTest"
    type="dmg"
    downloadURL="https://example.com/FreshTest.dmg"
    appNewVersion=$(versionFromGit owner repo)
    expectedTeamID="ABC123XYZ4"
    ;;
"""


def _fake_resolve_dynamic_to(version: str):
    """Stub resolve(): $(...) → ``version``, literals pass through."""
    from patcher_api.installomator.resolver import Resolved, Unresolvable

    def fake_resolve(
        expression,
        *,
        http_client=None,
        is_url=False,
        is_version=False,
        allow_subprocess_fallback=False,
        context=None,
    ):
        if expression is None:
            return Unresolvable(reason="none")
        if expression.startswith("$("):
            return Resolved(value=version)
        return Resolved(value=expression)

    return fake_resolve


@pytest.mark.asyncio
async def test_refresh_dynamic_resolutions_updates_unchanged(test_session, monkeypatch):
    """A SHA-unchanged dynamic label is re-resolved from stored raw, keeping it fresh."""
    from patcher_api.installomator.ingest import refresh_dynamic_resolutions

    # Initial ingest with resolution OFF: row stored, appNewVersion nulled,
    # raw keeps the shell expression.
    await ingest_installomator_labels(test_session, {"freshtest": _DYNAMIC_VERSION_FRAGMENT})
    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "freshtest")
    )
    assert label.app_new_version is None

    # Resolution ON + stubbed resolve. freshtest is NOT already-resolved this run.
    monkeypatch.setattr("patcher_api.installomator.ingest._RESOLVE_ON_INGEST", True)
    monkeypatch.setattr(
        "patcher_api.installomator.ingest.resolve", _fake_resolve_dynamic_to("5.5.5")
    )

    refreshed = await refresh_dynamic_resolutions(test_session, already_resolved=set())
    assert refreshed == 1

    updated = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "freshtest")
    )
    assert updated.app_new_version == "5.5.5"  # re-resolved from stored raw
    assert updated.download_url == "https://example.com/FreshTest.dmg"  # literal unchanged


@pytest.mark.asyncio
async def test_refresh_dynamic_resolutions_noop_when_disabled(test_session, monkeypatch):
    from patcher_api.installomator.ingest import refresh_dynamic_resolutions

    await ingest_installomator_labels(test_session, {"freshtest": _DYNAMIC_VERSION_FRAGMENT})
    monkeypatch.setattr("patcher_api.installomator.ingest._RESOLVE_ON_INGEST", False)

    assert await refresh_dynamic_resolutions(test_session, already_resolved=set()) == 0


@pytest.mark.asyncio
async def test_refresh_dynamic_resolutions_skips_already_resolved(test_session, monkeypatch):
    from patcher_api.installomator.ingest import refresh_dynamic_resolutions

    await ingest_installomator_labels(test_session, {"freshtest": _DYNAMIC_VERSION_FRAGMENT})
    monkeypatch.setattr("patcher_api.installomator.ingest._RESOLVE_ON_INGEST", True)
    monkeypatch.setattr(
        "patcher_api.installomator.ingest.resolve", _fake_resolve_dynamic_to("5.5.5")
    )

    # freshtest was freshly ingested this run → excluded from the refresh pass.
    refreshed = await refresh_dynamic_resolutions(test_session, already_resolved={"freshtest"})
    assert refreshed == 0


@pytest.mark.asyncio
async def test_refresh_dynamic_resolutions_skips_literal_only(test_session, monkeypatch):
    """Labels with no shell-expression projection aren't re-resolved (nothing drifts)."""
    from patcher_api.installomator.ingest import refresh_dynamic_resolutions

    literal_fragment = (
        "literaltest)\n"
        '    name="LiteralTest"\n'
        '    type="dmg"\n'
        '    downloadURL="https://example.com/Literal.dmg"\n'
        '    appNewVersion="1.2.3"\n'
        '    expectedTeamID="ABC123XYZ4"\n'
        "    ;;"
    )
    await ingest_installomator_labels(test_session, {"literaltest": literal_fragment})
    monkeypatch.setattr("patcher_api.installomator.ingest._RESOLVE_ON_INGEST", True)

    assert await refresh_dynamic_resolutions(test_session, already_resolved=set()) == 0


async def _stamp_macos(test_session, name: str, version: str, resolved_at) -> None:
    """Mark a label row as macOS-resolved with a known value + timestamp."""
    row = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == name)
    )
    row.app_new_version = version
    row.resolution_source = "macos"
    row.resolved_at = resolved_at
    await test_session.commit()


@pytest.mark.asyncio
async def test_refresh_defers_to_fresh_macos_resolution(test_session, monkeypatch):
    """A row a recent macOS pass owns is not re-resolved by the Linux fallback."""
    from datetime import UTC, datetime

    from patcher_api.installomator.ingest import refresh_dynamic_resolutions

    await ingest_installomator_labels(test_session, {"freshtest": _DYNAMIC_VERSION_FRAGMENT})
    await _stamp_macos(test_session, "freshtest", "1.2.3", datetime.now(UTC))

    monkeypatch.setattr("patcher_api.installomator.ingest._RESOLVE_ON_INGEST", True)
    monkeypatch.setattr(
        "patcher_api.installomator.ingest.resolve", _fake_resolve_dynamic_to("9.9.9")
    )

    assert await refresh_dynamic_resolutions(test_session, already_resolved=set()) == 0
    row = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "freshtest")
    )
    assert row.app_new_version == "1.2.3"  # macOS value preserved, not clobbered


@pytest.mark.asyncio
async def test_refresh_reclaims_stale_macos_resolution(test_session, monkeypatch):
    """Past the freshness window, the Linux fallback re-resolves a macOS-owned row."""
    from datetime import UTC, datetime, timedelta

    from patcher_api.installomator.ingest import refresh_dynamic_resolutions

    await ingest_installomator_labels(test_session, {"freshtest": _DYNAMIC_VERSION_FRAGMENT})
    await _stamp_macos(test_session, "freshtest", "1.2.3", datetime.now(UTC) - timedelta(days=30))

    monkeypatch.setattr("patcher_api.installomator.ingest._RESOLVE_ON_INGEST", True)
    monkeypatch.setattr(
        "patcher_api.installomator.ingest.resolve", _fake_resolve_dynamic_to("9.9.9")
    )

    assert await refresh_dynamic_resolutions(test_session, already_resolved=set()) == 1
    row = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "freshtest")
    )
    assert row.app_new_version == "9.9.9"  # stale macOS value reclaimed by Python


def test_set_resolve_on_ingest_toggles_the_flag(monkeypatch):
    """The --resolve CLI flag flips resolution on at runtime (bypassing env export)."""
    from patcher_api.installomator import ingest

    monkeypatch.setattr(ingest, "_RESOLVE_ON_INGEST", False)
    ingest.set_resolve_on_ingest(True)
    assert ingest._RESOLVE_ON_INGEST is True
