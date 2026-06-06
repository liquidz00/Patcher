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
from patcher_api.installomator.resolver import is_shell_expression
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.models.autopkg import AutopkgRecipe
from patcher_api.models.homebrew import HomebrewCask
from patcher_api.models.installomator import InstallomatorLabel
from patcher_api.models.jamf_app_installers import JamfAppInstaller
from patcher_api.models.mas import MasApp
from patcher_api.stitch import (
    _clean_cask_url,
    _extract_vendor,
    _find_matching_cask,
    _index_autopkg_by_name,
    _index_casks_by_app_name,
    _index_jai_by_title,
    _infer_install_method_from_cask,
    _jai_index_keys,
    _normalize_name,
    _resolve_download_url,
    _resolve_install_method,
    _resolve_version,
    _slugify,
    stitch_catalog,
)
from sqlalchemy import select

from patcher.policy import CURATED_BUNDLE_IDS


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


def _make_mas(
    *,
    bundle_id: str,
    name: str,
    version: str | None = None,
    artist_name: str | None = None,
    store_url: str | None = None,
) -> MasApp:
    """Build a :class:`MasApp` row for unit tests."""
    raw = {
        "bundleId": bundle_id,
        "trackName": name,
        "version": version,
        "artistName": artist_name,
        "trackViewUrl": store_url,
        "kind": "mac-software",
    }
    return MasApp(
        bundle_id=bundle_id,
        name=name,
        version=version,
        store_url=store_url,
        raw=raw,
        ingested_at=datetime.now(UTC),
    )


def _make_autopkg(
    *,
    identifier: str,
    name: str,
    shortname: str | None = None,
    repo: str = "autopkg/recipes",
    path: str | None = None,
    parent_identifier: str | None = None,
    inferred_type: str | None = None,
) -> AutopkgRecipe:
    """Build an :class:`AutopkgRecipe` row for unit tests."""
    shortname = shortname or f"{name}.download"
    path = path or f"{name}/{name}.download.recipe"
    return AutopkgRecipe(
        identifier=identifier,
        name=name,
        shortname=shortname,
        repo=repo,
        path=path,
        parent_identifier=parent_identifier,
        inferred_type=inferred_type or "download",
        description=None,
        raw={"name": name, "shortname": shortname, "repo": repo, "path": path},
        ingested_at=datetime.now(UTC),
    )


def _make_jai(
    *,
    title: str,
    source: str = "Jamf",
    host: str | None = None,
    bundle_id: str | None = None,
    version: str | None = None,
    download_url: str | None = None,
) -> JamfAppInstaller:
    """Build a :class:`JamfAppInstaller` row for unit tests."""
    return JamfAppInstaller(
        title=title,
        source=source,
        host=host,
        bundle_id=bundle_id,
        version=version,
        download_url=download_url,
        raw={"title": title, "source": source, "host": host},
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

    def test_falls_back_to_jai_when_label_and_cask_silent(self):
        """JAI's catalog version is the last-resort fallback after Installomator + Cask."""
        label = _make_label(name="x", app_new_version="$(curl -fs ...)")
        jai = _make_jai(title="X", version="3.2.1")
        assert _resolve_version(label, None, jai) == "3.2.1"

    def test_label_version_still_beats_jai(self):
        """JAI is the *fallback* — a literal label version still wins."""
        label = _make_label(name="x", app_new_version="121.0")
        jai = _make_jai(title="X", version="999.0")
        assert _resolve_version(label, None, jai) == "121.0"


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

    def test_falls_back_to_jai_external_url_when_label_and_cask_silent(self):
        """JAI's vendor URL (source=External) is the last-resort fallback."""
        label = _make_label(name="x", download_url="$(curl ...)")
        jai = _make_jai(
            title="X",
            source="External",
            download_url="https://vendor.example/x.pkg",
        )
        assert _resolve_download_url(label, None, jai) == "https://vendor.example/x.pkg"

    def test_does_not_use_jai_url_when_source_is_jamf(self):
        """
        Jamf-hosted JAI URLs are signed by Jamf, not the vendor — Installomator's
        Team-ID check would reject them. The resolver must not propagate one.
        """
        label = _make_label(name="x", download_url="$(curl ...)")
        jai = _make_jai(
            title="X",
            source="Jamf",
            download_url="https://appinstallers-packages.services.jamfcloud.com/x.pkg",
        )
        assert _resolve_download_url(label, None, jai) is None

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


class TestNormalizeName:
    """
    Cross-variant name normalization used to match AutoPkg recipe names
    against app display names. ``"Google Chrome"`` and ``"GoogleChrome"``
    must both normalize to the same key so either variant matches.
    """

    def test_simple_name(self):
        assert _normalize_name("Firefox") == "firefox"

    def test_whitespace_stripped(self):
        assert _normalize_name("Google Chrome") == "googlechrome"

    def test_concatenated_form_matches_whitespace_form(self):
        assert _normalize_name("GoogleChrome") == _normalize_name("Google Chrome")

    def test_punctuation_stripped(self):
        assert _normalize_name("Microsoft-Edge") == "microsoftedge"

    def test_none_returns_empty_string(self):
        assert _normalize_name(None) == ""

    def test_empty_returns_empty(self):
        assert _normalize_name("") == ""


class TestJaiIndexKeys:
    """JAI titles carry decoration the Installomator label name omits; the key
    generator strips it so a decorated title still matches a bare label."""

    def test_exact_title_is_first_key(self):
        assert _jai_index_keys("Firefox")[0] == "firefox"

    def test_trailing_version_dropped(self):
        keys = _jai_index_keys("Sublime Text 4")
        assert "sublimetext" in keys

    def test_trailing_year_dropped(self):
        assert "adobeaftereffects" in _jai_index_keys("Adobe After Effects 2025")

    def test_trailing_edition_words_dropped(self):
        # "DC Continuous" are both edition tokens.
        assert "adobeacrobatreader" in _jai_index_keys("Adobe Acrobat Reader DC Continuous")

    def test_leading_known_vendor_dropped(self):
        # The motivating case: SAP Privileges must reach the `privileges` label.
        assert "privileges" in _jai_index_keys("SAP Privileges")

    def test_leading_non_vendor_token_kept(self):
        # "Visual" isn't a vendor, so a real two-word name keeps its first word.
        keys = _jai_index_keys("Visual Studio")
        assert "studio" not in keys
        assert "visualstudio" in keys

    def test_dotted_version_dropped(self):
        assert "wireshark" in _jai_index_keys("Wireshark 4.6")


class TestIndexJaiByTitle:
    def test_decorated_title_indexed_under_bare_name(self):
        index = _index_jai_by_title([_make_jai(title="SAP Privileges")])
        assert index["privileges"].title == "SAP Privileges"
        assert index["sapprivileges"].title == "SAP Privileges"

    def test_exact_match_beats_decoration_stripped(self):
        # A bare "Privileges" title must own the "privileges" key even when a
        # "SAP Privileges" row also strips down to it.
        rows = [_make_jai(title="SAP Privileges"), _make_jai(title="Privileges")]
        index = _index_jai_by_title(rows)
        assert index["privileges"].title == "Privileges"

    def test_first_write_wins_on_stripped_collision(self):
        rows = [_make_jai(title="Wireshark 4.2"), _make_jai(title="Wireshark 4.6")]
        index = _index_jai_by_title(rows)
        assert index["wireshark"].title == "Wireshark 4.2"


class TestIndexAutopkgByName:
    def test_groups_multiple_recipes_by_name(self):
        recipes = [
            _make_autopkg(identifier="com.github.autopkg.download.Firefox", name="Firefox"),
            _make_autopkg(
                identifier="com.github.autopkg.munki.Firefox",
                name="Firefox",
                shortname="Firefox.munki",
                inferred_type="munki",
            ),
        ]
        index = _index_autopkg_by_name(recipes)
        assert len(index["firefox"]) == 2

    def test_separates_distinct_names(self):
        recipes = [
            _make_autopkg(identifier="com.github.autopkg.download.Firefox", name="Firefox"),
            _make_autopkg(identifier="com.github.autopkg.download.Chrome", name="Chrome"),
        ]
        index = _index_autopkg_by_name(recipes)
        assert set(index.keys()) == {"firefox", "chrome"}


class TestSlugify:
    """
    Used by phase 3 to derive a URL-friendly slug from a MAS app's
    ``trackName``. The exact normalization isn't load-bearing but the
    cases here protect against silent regressions.
    """

    def test_simple_name(self):
        assert _slugify("Pages") == "pages"

    def test_multi_word_name(self):
        assert _slugify("Final Cut Pro") == "final-cut-pro"

    def test_collapses_runs_of_non_alphanumerics(self):
        assert _slugify("OmniFocus 3 — Pro") == "omnifocus-3-pro"

    def test_strips_leading_and_trailing_punctuation(self):
        assert _slugify("...Things 3...") == "things-3"

    def test_returns_unknown_for_empty_input(self):
        assert _slugify("") == "unknown"

    def test_returns_unknown_for_all_punctuation_input(self):
        assert _slugify("!!!") == "unknown"

    def test_alphanumerics_are_lowercased(self):
        assert _slugify("BBEdit") == "bbedit"


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
    (
        il,
        cask_only,
        both,
        mas_only,
        mas_merged,
        autopkg_attached,
        jai_attached,
        failed,
    ) = await stitch_catalog(populated_session)

    # 3 Installomator labels → 3 Installomator-sourced apps
    assert il == 3
    # firefox + googlechromepkg should match Casks; onlyinstallomator shouldn't
    assert both == 2
    # `onlycask` is the only Cask not matched by an Installomator label
    assert cask_only == 1
    # No MAS records in this fixture → no MAS-only apps or merges
    assert mas_only == 0
    assert mas_merged == 0
    # No AutoPkg recipes in this fixture → no autopkg attachments
    assert autopkg_attached == 0
    # No JAI catalog rows in this fixture → no jamf_app_installer attachments
    assert jai_attached == 0
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
async def test_stitch_attaches_mas_when_installomator_bundle_id_matches(test_session):
    """
    An Installomator label whose ``package_id`` matches an existing
    :class:`MasApp.bundle_id` should produce an apps row with both
    ``installomator`` and ``mas`` in ``sources`` (canonical ordering) and
    both source-detail payloads populated.
    """
    test_session.add_all(
        [
            _make_label(
                name="microsoftword",
                display_name="Microsoft Word",
                install_type="pkg",
                package_id="com.microsoft.Word",
                download_url="https://example.com/word.pkg",
            ),
            _make_mas(
                bundle_id="com.microsoft.Word",
                name="Microsoft Word",
                version="16.83",
                artist_name="Microsoft Corporation",
                store_url="https://apps.apple.com/us/app/microsoft-word/id462054704",
            ),
        ]
    )
    await test_session.commit()

    await stitch_catalog(test_session)

    word = await test_session.scalar(select(AppRow).where(AppRow.slug == "microsoftword"))
    assert word is not None
    # Sources land in canonical order: installomator, homebrew_cask, autopkg, mas
    assert word.sources == ["installomator", "mas"]

    detail = await test_session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == word.id)
    )
    assert detail.installomator is not None
    assert detail.mas is not None
    assert detail.mas["bundle_id"] == "com.microsoft.Word"
    assert detail.mas["raw"]["artistName"] == "Microsoft Corporation"


@pytest.mark.asyncio
async def test_stitch_mas_only_record_creates_new_app_row(test_session):
    """
    A MAS record with no matching Installomator label produces a phase 3
    apps row with ``["mas"]`` as the only source, slug derived from the
    track name, and vendor pulled from ``artistName`` in the raw payload.
    """
    test_session.add(
        _make_mas(
            bundle_id="com.apple.iWork.Pages",
            name="Pages",
            version="14.2",
            artist_name="Apple",
            store_url="https://apps.apple.com/us/app/pages/id409201541",
        )
    )
    await test_session.commit()

    (
        il,
        cask_only,
        both,
        mas_only,
        mas_merged,
        autopkg_attached,
        jai_attached,
        failed,
    ) = await stitch_catalog(test_session)
    assert mas_only == 1
    assert failed == 0

    pages = await test_session.scalar(select(AppRow).where(AppRow.slug == "pages"))
    assert pages is not None
    assert pages.bundle_id == "com.apple.iWork.Pages"
    assert pages.name == "Pages"
    assert pages.vendor == "Apple"
    assert pages.current_version == "14.2"
    assert pages.sources == ["mas"]
    # MAS apps have no direct download URL; the App Store handles install
    assert pages.download_url is None

    detail = await test_session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == pages.id)
    )
    assert detail.installomator is None
    assert detail.homebrew_cask is None
    assert detail.mas is not None
    assert detail.mas["store_url"].startswith("https://apps.apple.com/")


@pytest.mark.asyncio
async def test_stitch_mas_slug_collision_merges_into_existing_row(test_session):
    """
    A MAS app whose slug collides with an existing apps row (typically a
    phase-2 Cask-only entry like "microsoft-word" or "xcode") gets MERGED
    into that row rather than skipped. The merge:

    1. Preserves the existing row's name/vendor/version/download_url.
    2. Appends "mas" to the row's sources list, reordered into canonical
       position.
    3. Writes the mas source_detail payload onto the existing
       app_source_details row.

    This is the fix for the empirical issue where Microsoft Office and
    Apple Pro Suite MAS apps were silently dropped because their slugified
    names already existed on the apps table from Homebrew Cask phase 2.
    """
    # Simulate a phase-2 Cask-only row at slug "microsoft-word" that the
    # MAS app for Microsoft Word would collide with.
    test_session.add_all(
        [
            _make_cask(
                token="microsoft-word",
                name="Microsoft Word",
                url="https://example.com/word.pkg",
                version="16.83",
            ),
            _make_mas(
                bundle_id="com.microsoft.Word",
                name="Microsoft Word",
                version="16.109",
                artist_name="Microsoft Corporation",
                store_url="https://apps.apple.com/us/app/microsoft-word/id462054704",
            ),
        ]
    )
    await test_session.commit()

    (
        il,
        cask_only,
        both,
        mas_only,
        mas_merged,
        autopkg_attached,
        jai_attached,
        failed,
    ) = await stitch_catalog(test_session)
    assert mas_only == 0
    assert mas_merged == 1
    assert failed == 0

    word = await test_session.scalar(select(AppRow).where(AppRow.slug == "microsoft-word"))
    assert word is not None
    # The cask row's fields are preserved (cask version, cask name, etc.)
    assert word.current_version == "16.83"
    assert word.name == "Microsoft Word"
    # "mas" added to sources in canonical order (homebrew_cask comes before mas)
    assert word.sources == ["homebrew_cask", "mas"]

    # Source detail row gained the mas payload while keeping the cask payload
    detail = await test_session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == word.id)
    )
    assert detail is not None
    assert detail.homebrew_cask is not None
    assert detail.mas is not None
    assert detail.mas["bundle_id"] == "com.microsoft.Word"


@pytest.mark.asyncio
async def test_stitch_attaches_autopkg_to_installomator_app(test_session):
    """
    AutoPkg recipes whose normalized name matches an Installomator label's
    display_name get attached as a source with the full list of matched
    recipes in the source_detail payload.
    """
    test_session.add_all(
        [
            _make_label(
                name="firefox",
                display_name="Firefox",
                install_type="pkg",
                package_id="org.mozilla.firefox",
                download_url="https://example.com/firefox.pkg",
            ),
            _make_autopkg(
                identifier="com.github.autopkg.download.Firefox",
                name="Firefox",
                shortname="Firefox.download",
                inferred_type="download",
            ),
            _make_autopkg(
                identifier="com.github.autopkg.munki.Firefox",
                name="Firefox",
                shortname="Firefox.munki",
                parent_identifier="com.github.autopkg.download.Firefox",
                inferred_type="munki",
            ),
        ]
    )
    await test_session.commit()

    _, _, _, _, _, autopkg_attached, _, _ = await stitch_catalog(test_session)
    assert autopkg_attached == 1

    firefox = await test_session.scalar(select(AppRow).where(AppRow.slug == "firefox"))
    # Canonical source ordering: installomator, homebrew_cask, autopkg, mas.
    # Cask + mas absent → just installomator + autopkg.
    assert firefox.sources == ["installomator", "autopkg"]

    detail = await test_session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == firefox.id)
    )
    recipes = detail.autopkg["recipes"]
    assert len(recipes) == 2
    assert {r["shortname"] for r in recipes} == {"Firefox.download", "Firefox.munki"}
    # Recipe URLs are constructed from repo + path (GitHub redirects master to main)
    assert all(
        r["recipe_url"].startswith("https://github.com/autopkg/recipes/blob/") for r in recipes
    )


@pytest.mark.asyncio
async def test_stitch_attaches_autopkg_to_cask_only_app(test_session):
    """Phase 2 (Cask-only) also gets AutoPkg attached by name match."""
    test_session.add_all(
        [
            _make_cask(
                token="alacritty", name="Alacritty", url="https://example.com/alacritty.dmg"
            ),
            _make_autopkg(
                identifier="com.github.autopkg.download.Alacritty",
                name="Alacritty",
            ),
        ]
    )
    await test_session.commit()

    await stitch_catalog(test_session)

    alacritty = await test_session.scalar(select(AppRow).where(AppRow.slug == "alacritty"))
    assert alacritty.sources == ["homebrew_cask", "autopkg"]


@pytest.mark.asyncio
async def test_stitch_attaches_autopkg_to_mas_only_app(test_session):
    """Phase 3 (MAS-only) also gets AutoPkg attached by name match."""
    test_session.add_all(
        [
            _make_mas(bundle_id="com.apple.dt.Xcode", name="Xcode", version="15.4"),
            _make_autopkg(identifier="com.github.autopkg.download.Xcode", name="Xcode"),
        ]
    )
    await test_session.commit()

    await stitch_catalog(test_session)

    xcode = await test_session.scalar(select(AppRow).where(AppRow.slug == "xcode"))
    # Canonical ordering puts autopkg before mas.
    assert xcode.sources == ["autopkg", "mas"]


@pytest.mark.asyncio
async def test_stitch_does_not_create_autopkg_only_apps(test_session):
    """
    An AutoPkg recipe with no matching app in Installomator / Cask / MAS
    should NOT generate a new ``apps`` row. AutoPkg is a coverage indicator,
    not an app source.
    """
    test_session.add(
        _make_autopkg(
            identifier="com.github.autopkg.download.SomeObscureApp",
            name="SomeObscureApp",
        )
    )
    await test_session.commit()

    _, _, _, _, _, autopkg_attached, _, _ = await stitch_catalog(test_session)
    assert autopkg_attached == 0

    apps = (await test_session.scalars(select(AppRow))).all()
    # Seed apps from conftest may exist but no new row from the orphan recipe
    assert not any(a.name == "SomeObscureApp" for a in apps)


@pytest.mark.asyncio
async def test_stitch_matches_autopkg_across_name_variants(test_session):
    """
    Normalized matching: ``"Google Chrome"`` label display_name should
    match an AutoPkg recipe named ``"GoogleChrome"`` (concatenated form),
    and vice versa.
    """
    test_session.add_all(
        [
            _make_label(
                name="googlechrome",
                display_name="Google Chrome",
                install_type="pkg",
                package_id="com.google.Chrome",
                download_url="https://example.com/chrome.pkg",
            ),
            _make_autopkg(
                identifier="com.github.autopkg.download.GoogleChrome",
                name="GoogleChrome",
            ),
        ]
    )
    await test_session.commit()

    await stitch_catalog(test_session)

    chrome = await test_session.scalar(select(AppRow).where(AppRow.slug == "googlechrome"))
    assert "autopkg" in chrome.sources


@pytest.mark.asyncio
async def test_stitch_attaches_jai_to_installomator_app(test_session):
    """
    A JAI catalog row whose normalized title matches an Installomator
    label's display_name gets attached as a source, with the title/source/
    host preserved in the source_detail payload.
    """
    test_session.add_all(
        [
            _make_label(
                name="firefox",
                display_name="Firefox",
                install_type="pkg",
                package_id="org.mozilla.firefox",
                download_url="https://example.com/firefox.pkg",
            ),
            _make_jai(title="Firefox", source="External", host="download.mozilla.org"),
        ]
    )
    await test_session.commit()

    _, _, _, _, _, _, jai_attached, _ = await stitch_catalog(test_session)
    assert jai_attached == 1

    firefox = await test_session.scalar(select(AppRow).where(AppRow.slug == "firefox"))
    # Canonical ordering: installomator, homebrew_cask, autopkg, jamf_app_installer, mas.
    assert firefox.sources == ["installomator", "jamf_app_installer"]

    detail = await test_session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == firefox.id)
    )
    assert detail.jamf_app_installer == {
        "title": "Firefox",
        "source": "External",
        "host": "download.mozilla.org",
        "bundle_id": None,
        "version": None,
        "jamf_id": None,
        "download_url": None,
        "architecture": None,
    }


@pytest.mark.asyncio
async def test_stitch_matches_jai_by_bundle_id_over_name(test_session):
    """
    bundle_id is the precision overlay: a JAI title with a matching bundle_id
    attaches even when its name wouldn't normalize to the label's name.
    """
    test_session.add_all(
        [
            _make_label(
                name="someapp",
                display_name="Some App",
                install_type="pkg",
                package_id="com.vendor.someapp",
                download_url="https://example.com/someapp.pkg",
            ),
            # Name ("Vendor Bundle Suite") would NOT name-match "Some App";
            # the bundle_id does.
            _make_jai(
                title="Vendor Bundle Suite",
                source="Jamf",
                bundle_id="com.vendor.someapp",
            ),
        ]
    )
    await test_session.commit()

    _, _, _, _, _, _, jai_attached, _ = await stitch_catalog(test_session)
    assert jai_attached == 1

    app = await test_session.scalar(select(AppRow).where(AppRow.slug == "someapp"))
    assert "jamf_app_installer" in app.sources


@pytest.mark.asyncio
async def test_stitch_backfills_bundle_id_from_jai_onto_cask_only_app(test_session):
    """
    A Cask-only app has no bundle_id; a name-matched JAI title that has one
    backfills it onto the app (JAI as a bundle_id provider).
    """
    test_session.add_all(
        [
            _make_cask(token="bartender", name="Bartender", version="5.0"),
            _make_jai(title="Bartender", source="Jamf", bundle_id="com.surteesstudios.Bartender"),
        ]
    )
    await test_session.commit()

    await stitch_catalog(test_session)

    app = await test_session.scalar(select(AppRow).where(AppRow.slug == "bartender"))
    assert app.bundle_id == "com.surteesstudios.Bartender"  # backfilled from JAI
    assert "jamf_app_installer" in app.sources


@pytest.mark.asyncio
async def test_stitch_attaches_jai_to_cask_only_app(test_session):
    """Phase 2 (Cask-only) also gets JAI attached by name match."""
    test_session.add_all(
        [
            _make_cask(token="alttab", name="AltTab", url="https://example.com/alttab.dmg"),
            _make_jai(title="AltTab", source="External", host="github.com"),
        ]
    )
    await test_session.commit()

    await stitch_catalog(test_session)

    alttab = await test_session.scalar(select(AppRow).where(AppRow.slug == "alttab"))
    assert "jamf_app_installer" in alttab.sources


@pytest.mark.asyncio
async def test_stitch_attaches_jai_to_mas_only_app(test_session):
    """Phase 3 (MAS-only) also gets JAI attached by name match."""
    test_session.add_all(
        [
            _make_mas(bundle_id="com.example.Xcode", name="Xcode", version="15.4"),
            _make_jai(title="Xcode", source="Jamf", host=None),
        ]
    )
    await test_session.commit()

    await stitch_catalog(test_session)

    xcode = await test_session.scalar(select(AppRow).where(AppRow.slug == "xcode"))
    # Canonical ordering puts jamf_app_installer before mas.
    assert xcode.sources == ["jamf_app_installer", "mas"]


@pytest.mark.asyncio
async def test_stitch_does_not_create_jai_only_apps(test_session):
    """
    A JAI title with no matching app in Installomator / Cask / MAS does
    NOT generate a new apps row. JAI is a coverage indicator, not an app
    source.
    """
    test_session.add(_make_jai(title="SomeObscureApp", source="Jamf"))
    await test_session.commit()

    _, _, _, _, _, _, jai_attached, _ = await stitch_catalog(test_session)
    assert jai_attached == 0

    apps = (await test_session.scalars(select(AppRow))).all()
    assert not any(a.name == "SomeObscureApp" for a in apps)


@pytest.mark.asyncio
async def test_stitch_canonical_source_ordering_with_all_five(test_session):
    """
    When an app has every possible source attached, the ``sources`` list
    lands in the canonical order regardless of insertion order. This
    pinned ordering is what downstream filter logic expects.
    """
    test_session.add_all(
        [
            _make_label(
                name="firefox",
                display_name="Firefox",
                install_type="pkg",
                package_id="org.mozilla.firefox",
                download_url="https://example.com/firefox.pkg",
            ),
            _make_cask(
                token="firefox",
                name="Firefox",
                url="https://example.com/firefox.dmg",
                artifacts=[{"app": ["Firefox.app"]}],
            ),
            _make_autopkg(identifier="com.github.autopkg.download.Firefox", name="Firefox"),
            _make_mas(bundle_id="org.mozilla.firefox", name="Firefox", version="125.0"),
            _make_jai(title="Firefox", source="External", host="download.mozilla.org"),
        ]
    )
    await test_session.commit()

    await stitch_catalog(test_session)

    firefox = await test_session.scalar(select(AppRow).where(AppRow.slug == "firefox"))
    assert firefox.sources == [
        "installomator",
        "homebrew_cask",
        "autopkg",
        "jamf_app_installer",
        "mas",
    ]


@pytest.mark.asyncio
async def test_stitch_is_idempotent(populated_session):
    """Running stitch twice should yield the same row count, not duplicates."""
    await stitch_catalog(populated_session)
    first_count = len((await populated_session.scalars(select(AppRow))).all())

    await stitch_catalog(populated_session)
    second_count = len((await populated_session.scalars(select(AppRow))).all())

    assert first_count == second_count


@pytest.mark.asyncio
async def test_stitch_curated_bundle_id_attaches_jai_to_label(test_session):
    """
    A label whose slug is in CURATED_BUNDLE_IDS but carries no package_id
    attaches JAI via the seeded bundle_id, which the decorated-name path misses.
    """
    test_session.add_all(
        [
            _make_label(name="zoom", display_name="zoom.us", install_type="pkg"),
            _make_jai(title="Zoom Client for Meetings", bundle_id=CURATED_BUNDLE_IDS["zoom"]),
        ]
    )
    await test_session.commit()

    await stitch_catalog(test_session)

    zoom = await test_session.scalar(select(AppRow).where(AppRow.slug == "zoom"))
    assert "jamf_app_installer" in zoom.sources
    assert zoom.bundle_id == CURATED_BUNDLE_IDS["zoom"]


@pytest.mark.asyncio
async def test_stitch_curated_bundle_id_attaches_jai_to_cask(test_session):
    """Same as above for a cask-only slug (the phase-2 injection point)."""
    test_session.add_all(
        [
            _make_cask(token="obs", name="OBS"),
            _make_jai(title="OBS Studio", bundle_id=CURATED_BUNDLE_IDS["obs"]),
        ]
    )
    await test_session.commit()

    await stitch_catalog(test_session)

    obs = await test_session.scalar(select(AppRow).where(AppRow.slug == "obs"))
    assert "jamf_app_installer" in obs.sources
    assert obs.bundle_id == CURATED_BUNDLE_IDS["obs"]
