"""
Tests for the catalog stitch logic.

Unit-tests cover the pure helpers (vendor extraction, version/URL resolution,
install-method mapping, match strategies). Integration-style tests seed a
fresh DB with handful of Installomator labels + Cask records, run the full
stitch, and assert on the resulting ``apps`` rows.
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.models.homebrew import HomebrewCask
from patcher_api.models.installomator import InstallomatorLabel
from patcher_api.stitch import (
    _clean_cask_url,
    _extract_vendor,
    _find_matching_cask,
    _index_casks_by_app_name,
    _infer_install_method_from_cask,
    _resolve_download_url,
    _resolve_install_method,
    _resolve_version,
    stitch_catalog,
)
from sqlalchemy import select

from patcher.core.installomator import is_shell_expression


def _make_label(
    *,
    name: str,
    display_name: str | None = None,
    install_type: str | None = "dmg",
    package_id: str | None = None,
    download_url: str | None = None,
    app_new_version: str | None = None,
    raw: dict | None = None,
) -> InstallomatorLabel:
    """Build an :class:`InstallomatorLabel` row for unit tests."""
    return InstallomatorLabel(
        name=name,
        display_name=display_name,
        install_type=install_type,
        package_id=package_id,
        download_url=download_url,
        app_new_version=app_new_version,
        expected_team_id="TESTTEAMID",
        raw=raw or {},
        ingested_at=datetime.now(UTC),
    )


def _make_cask(
    *,
    token: str,
    name: str | None = None,
    url: str | None = None,
    version: str | None = None,
    sha256: str | None = None,
    artifacts: list[dict] | None = None,
) -> HomebrewCask:
    """Build a :class:`HomebrewCask` row for unit tests."""
    raw = {
        "token": token,
        "name": [name] if name else [],
        "url": url,
        "version": version,
        "sha256": sha256,
        "artifacts": artifacts or [],
    }
    return HomebrewCask(
        token=token,
        name=name or token,
        url=url,
        version=version,
        sha256=sha256,
        raw=raw,
        ingested_at=datetime.now(UTC),
    )


# ----- pure-helper unit tests -----


class TestIsShellExpression:
    def test_literal_string_is_not_shell_expression(self):
        assert not is_shell_expression("121.0")

    def test_dollar_parenis_shell_expression(self):
        assert is_shell_expression("$(curl -fs example.com)")

    def test_none_is_not_shell_expression(self):
        assert not is_shell_expression(None)


class TestExtractVendor:
    def test_extracts_from_reverse_dns_package_id(self):
        label = _make_label(name="firefox", package_id="com.mozilla.firefox")
        assert _extract_vendor(label) == "Mozilla"

    def test_skips_org_tld(self):
        label = _make_label(name="thunderbird", package_id="org.mozilla.thunderbird")
        assert _extract_vendor(label) == "Mozilla"

    def test_non_tld_first_segment_is_used(self):
        label = _make_label(name="thing", package_id="acme.thing")
        assert _extract_vendor(label) == "Acme"

    def test_falls_back_to_first_word_of_display_name(self):
        label = _make_label(name="thing", display_name="Acme Widget Pro")
        assert _extract_vendor(label) == "Acme"

    def test_returns_none_when_no_signal(self):
        label = _make_label(name="thing")
        assert _extract_vendor(label) is None


class TestResolveVersion:
    def test_prefers_literal_label_version(self):
        label = _make_label(name="firefox", app_new_version="121.0")
        cask = _make_cask(token="firefox", version="120.0")
        assert _resolve_version(label, cask) == "121.0"

    def test_falls_back_to_cask_when_labelis_shell_expression(self):
        label = _make_label(name="firefox", app_new_version="$(curl -fs ...)")
        cask = _make_cask(token="firefox", version="120.0")
        assert _resolve_version(label, cask) == "120.0"

    def test_returns_none_when_neither_resolves(self):
        label = _make_label(name="firefox", app_new_version="$(curl -fs ...)")
        assert _resolve_version(label, None) is None


class TestResolveDownloadUrl:
    def test_prefers_literal_label_url(self):
        label = _make_label(name="firefox", download_url="https://mozilla.org/firefox.dmg")
        cask = _make_cask(token="firefox", url="https://cask.example/firefox.dmg")
        assert _resolve_download_url(label, cask) == "https://mozilla.org/firefox.dmg"

    def test_falls_back_to_cask_when_label_urlis_shell_expression(self):
        label = _make_label(name="firefox", download_url="$(curl ...)")
        cask = _make_cask(token="firefox", url="https://cask.example/firefox.dmg")
        assert _resolve_download_url(label, cask) == "https://cask.example/firefox.dmg"

    def test_falls_back_to_cask_when_label_url_is_html_body(self):
        """
        Regression: even if ingest stored an HTML error page in the label's
        download_url (pre-validator data, or a future regression), stitch
        must reject it and fall back to the Cask URL rather than propagate
        garbage into ``apps.download_url``.
        """
        label = _make_label(name="firefox", download_url="<!doctype html><html>error</html>")
        cask = _make_cask(token="firefox", url="https://cask.example/firefox.dmg")
        assert _resolve_download_url(label, cask) == "https://cask.example/firefox.dmg"

    def test_falls_back_to_cask_when_label_url_is_multi_line(self):
        label = _make_label(
            name="firefox",
            download_url="https://example.com/v1.dmg\nhttps://example.com/v2.dmg",
        )
        cask = _make_cask(token="firefox", url="https://cask.example/firefox.dmg")
        assert _resolve_download_url(label, cask) == "https://cask.example/firefox.dmg"

    def test_falls_back_to_cask_when_label_url_is_ftp(self):
        label = _make_label(name="grads", download_url="ftp://cola.gmu.edu/grads/foo.tar.gz")
        cask = _make_cask(token="grads", url="https://cask.example/grads.dmg")
        assert _resolve_download_url(label, cask) == "https://cask.example/grads.dmg"

    def test_returns_none_when_both_sides_are_garbage(self):
        """If both the label and the cask URLs fail sanity checks, no fallback."""
        label = _make_label(name="weird", download_url="ftp://example.com/foo.dmg")
        cask = _make_cask(token="weird", url="<!doctype html><html>error</html>")
        assert _resolve_download_url(label, cask) is None


class TestCleanCaskUrl:
    """
    Used by both the phase 1 fallback in :func:`_resolve_download_url` and
    the phase 2 direct insert in :func:`stitch_catalog` for Cask-only
    apps. The phase 2 path is the one that bit production: a Cask with an
    ``ftp://`` URL would bypass the phase 1 validator and land in
    ``apps.download_url``, then trip ``HttpUrl`` at response time.
    """

    def test_clean_http_url_returned(self):
        cask = _make_cask(token="firefox", url="https://example.com/foo.dmg")
        assert _clean_cask_url(cask) == "https://example.com/foo.dmg"

    def test_none_cask_returns_none(self):
        assert _clean_cask_url(None) is None

    def test_cask_without_url_returns_none(self):
        cask = _make_cask(token="firefox", url=None)
        assert _clean_cask_url(cask) is None

    def test_ftp_url_returns_none(self):
        cask = _make_cask(token="grads", url="ftp://cola.gmu.edu/grads/foo.tar.gz")
        assert _clean_cask_url(cask) is None

    def test_html_body_url_returns_none(self):
        cask = _make_cask(token="weird", url="<!doctype html><html>oops</html>")
        assert _clean_cask_url(cask) is None


class TestResolveInstallMethod:
    def test_known_type_is_returned(self):
        assert _resolve_install_method("pkg") == "pkg"

    def test_unknown_type_returns_none(self):
        assert _resolve_install_method("weird-format") is None

    def test_none_returns_none(self):
        assert _resolve_install_method(None) is None


class TestInferInstallMethodFromCask:
    def test_dmg_url(self):
        cask = _make_cask(token="x", url="https://example.com/foo.dmg")
        assert _infer_install_method_from_cask(cask) == "dmg"

    def test_pkg_url(self):
        cask = _make_cask(token="x", url="https://example.com/foo.pkg")
        assert _infer_install_method_from_cask(cask) == "pkg"

    def test_unrecognized_url_returns_none(self):
        cask = _make_cask(token="x", url="https://example.com/foo.rpm")
        assert _infer_install_method_from_cask(cask) is None


class TestIndexCasksByAppName:
    def test_indexes_first_app_in_each_artifact(self):
        cask = _make_cask(
            token="firefox",
            artifacts=[{"app": ["Firefox.app"]}, {"zap": []}],
        )
        index = _index_casks_by_app_name([cask])
        assert index["Firefox.app"] is cask

    def test_skips_artifacts_without_app_key(self):
        cask = _make_cask(token="x", artifacts=[{"pkg": ["thing.pkg"]}])
        index = _index_casks_by_app_name([cask])
        assert index == {}

    def test_first_cask_wins_on_collision(self):
        first = _make_cask(token="a", artifacts=[{"app": ["Shared.app"]}])
        second = _make_cask(token="b", artifacts=[{"app": ["Shared.app"]}])
        index = _index_casks_by_app_name([first, second])
        assert index["Shared.app"] is first


class TestFindMatchingCask:
    def test_strategy_1_token_match(self):
        label = _make_label(name="firefox", display_name="Firefox")
        cask = _make_cask(token="firefox", artifacts=[{"app": ["Firefox.app"]}])
        match = _find_matching_cask(label, {"firefox": cask}, {"Firefox.app": cask})
        assert match is cask

    def test_strategy_2_app_name_match_when_token_differs(self):
        label = _make_label(name="firefoxpkg", display_name="Firefox")
        cask = _make_cask(token="firefox", artifacts=[{"app": ["Firefox.app"]}])
        match = _find_matching_cask(label, {"firefox": cask}, {"Firefox.app": cask})
        assert match is cask

    def test_no_match_returns_none(self):
        label = _make_label(name="noisbo", display_name="No Such Bo")
        match = _find_matching_cask(label, {}, {})
        assert match is None


# ----- integration-style tests against an in-memory DB -----


@pytest_asyncio.fixture
async def populated_session(test_session):
    """Populate the test DB with a small set of Installomator + Cask records."""
    test_session.add_all(
        [
            _make_label(
                name="firefox",
                display_name="Firefox",
                install_type="pkg",
                package_id="org.mozilla.firefox",
                download_url="https://mozilla.org/firefox.pkg",
                app_new_version="121.0",
                raw={"name": "Firefox", "type": "pkg"},
            ),
            _make_label(
                name="googlechromepkg",
                display_name="Google Chrome",
                install_type="pkg",
                package_id="com.google.Chrome",
                download_url="$(curl -fs ...)",
                app_new_version="$(curl -fs ...)",
                raw={"name": "Google Chrome", "type": "pkg"},
            ),
            _make_label(
                name="onlyinstallomator",
                display_name="Only Installomator",
                install_type="dmg",
                package_id="com.example.onlyinstallomator",
                download_url="https://example.com/onlyinstallomator.dmg",
                app_new_version="1.0",
                raw={"name": "Only Installomator", "type": "dmg"},
            ),
        ]
    )
    test_session.add_all(
        [
            _make_cask(
                token="firefox",
                name="Mozilla Firefox",
                url="https://download.mozilla.org/firefox.dmg",
                version="121.0",
                sha256="no_check",
                artifacts=[{"app": ["Firefox.app"]}],
            ),
            _make_cask(
                token="google-chrome",
                name="Google Chrome",
                url="https://dl.google.com/chrome.dmg",
                version="120.0",
                sha256="no_check",
                artifacts=[{"app": ["Google Chrome.app"]}],
            ),
            _make_cask(
                token="onlycask",
                name="Only Cask",
                url="https://example.com/onlycask.dmg",
                version="2.5",
                sha256="no_check",
                artifacts=[{"app": ["Only Cask.app"]}],
            ),
        ]
    )
    await test_session.commit()
    return test_session


@pytest.mark.asyncio
async def test_stitch_returns_correct_counts(populated_session):
    il, cask_only, both, failed = await stitch_catalog(populated_session)

    # 3 Installomator labels → 3 Installomator-sourced apps
    assert il == 3
    # firefox + googlechromepkg should match Casks; onlyinstallomator shouldn't
    assert both == 2
    # `onlycask` is the only Cask not matched by an Installomator label
    assert cask_only == 1
    assert failed == 0


@pytest.mark.asyncio
async def test_stitch_token_match_attaches_cask_source(populated_session):
    await stitch_catalog(populated_session)

    firefox = await populated_session.scalar(select(AppRow).where(AppRow.slug == "firefox"))
    assert firefox is not None
    assert firefox.bundle_id == "org.mozilla.firefox"
    assert firefox.vendor == "Mozilla"
    assert firefox.current_version == "121.0"
    assert "installomator" in firefox.sources
    assert "homebrew_cask" in firefox.sources

    detail = await populated_session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == firefox.id)
    )
    assert detail.installomator["label_name"] == "firefox"
    assert detail.homebrew_cask["token"] == "firefox"


@pytest.mark.asyncio
async def test_stitch_appname_match_attaches_cask_source(populated_session):
    """googlechromepkg label should match the google-chrome cask via 'Google Chrome.app'."""
    await stitch_catalog(populated_session)

    chrome = await populated_session.scalar(select(AppRow).where(AppRow.slug == "googlechromepkg"))
    assert chrome is not None
    assert "homebrew_cask" in chrome.sources
    # Shell-expression URLs fall back to Cask URL
    assert chrome.download_url == "https://dl.google.com/chrome.dmg"
    # Shell-expression version falls back to Cask version
    assert chrome.current_version == "120.0"

    detail = await populated_session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == chrome.id)
    )
    assert detail.homebrew_cask["token"] == "google-chrome"


@pytest.mark.asyncio
async def test_stitch_installomator_only_label(populated_session):
    await stitch_catalog(populated_session)

    only_il = await populated_session.scalar(
        select(AppRow).where(AppRow.slug == "onlyinstallomator")
    )
    assert only_il is not None
    assert only_il.sources == ["installomator"]
    assert only_il.download_url == "https://example.com/onlyinstallomator.dmg"

    detail = await populated_session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == only_il.id)
    )
    assert detail.installomator is not None
    assert detail.homebrew_cask is None


@pytest.mark.asyncio
async def test_stitch_cask_only_record(populated_session):
    await stitch_catalog(populated_session)

    only_cask = await populated_session.scalar(select(AppRow).where(AppRow.slug == "onlycask"))
    assert only_cask is not None
    assert only_cask.sources == ["homebrew_cask"]
    assert only_cask.bundle_id is None
    assert only_cask.current_version == "2.5"
    # Cask-only records infer install_method from the URL extension
    assert only_cask.install_method == "dmg"

    detail = await populated_session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == only_cask.id)
    )
    assert detail.installomator is None
    assert detail.homebrew_cask["token"] == "onlycask"


@pytest.mark.asyncio
async def test_stitch_cask_only_record_with_ftp_url_nulls_download_url(test_session):
    """
    Regression: phase 2 of :func:`stitch_catalog` previously assigned
    ``cask.url`` directly to ``apps.download_url`` without sanity-checking
    it. A cask with an ``ftp://`` URL (e.g. the ``grads`` cask sourcing
    from ``cola.gmu.edu``) would then trip the response model's ``HttpUrl``
    validation, surfacing as a 500 on ``/apps``. Phase 2 now gates the
    cask URL through :func:`_clean_cask_url`.
    """
    test_session.add(
        _make_cask(
            token="grads",
            name="GrADS",
            url="ftp://cola.gmu.edu/grads/2.2/grads-2.2.1-bin-darwin17.5.tar.gz",
            version="2.2.1",
            sha256="no_check",
            artifacts=[{"app": ["GrADS.app"]}],
        )
    )
    await test_session.commit()

    await stitch_catalog(test_session)

    grads_app = await test_session.scalar(select(AppRow).where(AppRow.slug == "grads"))
    assert grads_app is not None
    # FTP URL was nulled by the validator gate, not propagated verbatim.
    assert grads_app.download_url is None
    # The cask source detail still carries the original URL for traceability.
    detail = await test_session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == grads_app.id)
    )
    assert detail.homebrew_cask["cask_json"]["url"].startswith("ftp://")


@pytest.mark.asyncio
async def test_stitch_is_idempotent(populated_session):
    """Running stitch twice should yield the same row count, not duplicates."""
    await stitch_catalog(populated_session)
    first_count = len((await populated_session.scalars(select(AppRow))).all())

    await stitch_catalog(populated_session)
    second_count = len((await populated_session.scalars(select(AppRow))).all())

    assert first_count == second_count
