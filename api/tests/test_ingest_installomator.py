"""
Tests for Installomator label ingestion.

Uses inline fixture fragments rather than hitting GitHub — fast, deterministic,
offline. The fragments are real Installomator label syntax (verified against
the upstream repo); changes here should track upstream label format changes.
"""

import pytest
from patcher_api.ingest.installomator import (
    IGNORED_TEAMS,
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


@pytest.mark.asyncio
async def test_ingest_stores_realistic_label(test_session, monkeypatch):
    # Enable the opt-in resolver path for this test, AND mock the underlying
    # resolve() so it stays offline + deterministic. The Firefox label's
    # appNewVersion is a curl pipeline; we don't want the test suite hitting
    # download.mozilla.org. Stub returns a fixed version for the curl
    # expression, passes literals through unchanged.
    from patcher_api.installomator_resolver import Resolved, Unresolvable

    monkeypatch.setattr("patcher_api.ingest.installomator._RESOLVE_ON_INGEST", True)

    def fake_resolve(
        expression, *, http_client=None, is_url=False, allow_subprocess_fallback=False
    ):
        if expression is None:
            return Unresolvable(reason="none")
        if expression.startswith("$("):
            return Resolved(value="121.0")
        return Resolved(value=expression)

    monkeypatch.setattr("patcher_api.ingest.installomator.resolve", fake_resolve)

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
    from patcher_api.installomator_resolver import (
        InvalidOutput,
        Resolved,
        looks_like_clean_http_url,
    )

    monkeypatch.setattr("patcher_api.ingest.installomator._RESOLVE_ON_INGEST", True)

    html_body = (
        '<!doctype html><html lang="en"><head><title>HTTP Status 400'
        "</title></head><body><h1>Bad Request</h1></body></html>"
    )

    def fake_resolve(
        expression, *, http_client=None, is_url=False, allow_subprocess_fallback=False
    ):
        value = html_body if expression and expression.startswith("$(") else expression
        if is_url and value is not None and not looks_like_clean_http_url(value):
            return InvalidOutput(raw=value, reason="bad url")
        return Resolved(value=value)

    monkeypatch.setattr("patcher_api.ingest.installomator.resolve", fake_resolve)

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
    from patcher_api.installomator_resolver import (
        InvalidOutput,
        Resolved,
        looks_like_clean_http_url,
    )

    monkeypatch.setattr("patcher_api.ingest.installomator._RESOLVE_ON_INGEST", True)

    multi_line = (
        "https://example.com/app-2.6.5.dmg\n"
        "https://example.com/app-2.6.4.dmg\n"
        "https://example.com/app-2.6.3.dmg"
    )

    def fake_resolve(
        expression, *, http_client=None, is_url=False, allow_subprocess_fallback=False
    ):
        value = multi_line if expression and expression.startswith("$(") else expression
        if is_url and value is not None and not looks_like_clean_http_url(value):
            return InvalidOutput(raw=value, reason="bad url")
        return Resolved(value=value)

    monkeypatch.setattr("patcher_api.ingest.installomator.resolve", fake_resolve)

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
    from patcher_api.installomator_resolver import (
        InvalidOutput,
        Resolved,
        looks_like_clean_http_url,
    )

    monkeypatch.setattr("patcher_api.ingest.installomator._RESOLVE_ON_INGEST", True)

    ftp_url = "ftp://cola.gmu.edu/grads/foo.tar.gz"

    def fake_resolve(
        expression, *, http_client=None, is_url=False, allow_subprocess_fallback=False
    ):
        value = ftp_url if expression and expression.startswith("$(") else expression
        if is_url and value is not None and not looks_like_clean_http_url(value):
            return InvalidOutput(raw=value, reason="bad url")
        return Resolved(value=value)

    monkeypatch.setattr("patcher_api.ingest.installomator.resolve", fake_resolve)

    ingested, skipped, failed = await ingest_installomator_labels(
        test_session, {"garbagelabel": SHELL_DOWNLOAD_FRAGMENT}
    )

    assert ingested == 1
    label = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "garbagelabel")
    )
    assert label.download_url is None


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
    from patcher_api.ingest import installomator as ingest_module

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

    # One row succeeds (the first); the second blows up and is counted as failed.
    assert ingested == 1
    assert failed == 1
    labels = (await test_session.scalars(select(InstallomatorLabel))).all()
    assert len(labels) == 1
    assert labels[0].name == "firefoxpkg"
