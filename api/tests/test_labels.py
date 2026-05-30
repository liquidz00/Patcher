"""
Tests for :mod:`patcher_api.labels` — pure-function projection logic.

The route layer is tested separately in ``test_apps.py``. Here we exercise
:func:`build_installomator_label` directly with hand-built ``AppRow`` /
``AppSourceDetail`` instances, asserting on the resolved field values and
the warnings emitted.
"""

import pytest
from patcher_api.labels import build_installomator_label
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow


def _make_app(
    *,
    slug: str = "firefox",
    name: str | None = "Firefox",
    install_method: str | None = "dmg",
    download_url: str | None = "https://example.com/firefox.dmg",
    current_version: str | None = "121.0",
) -> AppRow:
    """Build a minimal ``AppRow`` for unit tests."""
    return AppRow(
        id=1,
        slug=slug,
        bundle_id=None,
        name=name,
        vendor=None,
        current_version=current_version,
        latest_release_date=None,
        download_url=download_url,
        install_method=install_method,
        sha256=None,
        sources=[],
    )


def _make_detail(
    *,
    installomator: dict | None = None,
    homebrew_cask: dict | None = None,
    jamf_app_installer: dict | None = None,
) -> AppSourceDetailRow:
    return AppSourceDetailRow(
        app_id=1,
        installomator=installomator,
        homebrew_cask=homebrew_cask,
        autopkg=None,
        jamf_app_installer=jamf_app_installer,
    )


_JAI_EXTERNAL = {
    "title": "ChatGPT Atlas",
    "source": "External",
    "host": "vendor.example",
    "bundle_id": "com.openai.atlas",
    "version": "1.0.0",
    "jamf_id": "999",
    "download_url": "https://vendor.example/ChatGPT-Atlas.pkg",
    "architecture": "universal",
}


class TestBuildInstallomatorLabel:
    def test_both_sources_produce_complete_label(self):
        app = _make_app()
        detail = _make_detail(
            installomator={
                "label_name": "firefox",
                "label_url": "https://github.com/.../firefox.sh",
                "raw": {
                    "name": "Firefox",
                    "type": "dmg",
                    "expectedTeamID": "43AQ936H96",
                },
            },
            homebrew_cask={
                "token": "firefox",
                "cask_json": {
                    "token": "firefox",
                    "name": ["Mozilla Firefox"],
                    "url": "https://download.mozilla.org/firefox.dmg",
                    "version": "121.0",
                },
            },
        )

        result = build_installomator_label(app, detail)

        assert result.label_name == "firefox"
        assert result.warnings == []
        assert "installomator" in result.sources_used
        assert "homebrew_cask" in result.sources_used

        content = result.content
        # Cask name wins over apps row + installomator name
        assert content["name"] == "Mozilla Firefox"
        # Installomator type used
        assert content["type"] == "dmg"
        # Cask URL preferred over installomator's downloadURL
        assert content["downloadURL"] == "https://download.mozilla.org/firefox.dmg"
        # apps row version
        assert content["appNewVersion"] == "121.0"
        # Team ID from Installomator
        assert content["expectedTeamID"] == "43AQ936H96"

    def test_cask_only_app_warns_about_missing_team_id(self):
        """Cask-only apps have no expectedTeamID — must warn loudly."""
        app = _make_app(install_method="pkg")
        detail = _make_detail(
            homebrew_cask={
                "token": "obscureapp",
                "cask_json": {
                    "token": "obscureapp",
                    "name": ["Obscure App"],
                    "url": "https://example.com/obscure.pkg",
                    "version": "2.0",
                },
            },
        )

        result = build_installomator_label(app, detail)

        # Field is omitted from content (key not present)
        assert "expectedTeamID" not in result.content
        # Warning surfaces the issue
        assert any("expectedTeamID" in w for w in result.warnings)
        assert result.sources_used == ["homebrew_cask"]

    def test_installomator_only_app_uses_installomator_values(self):
        app = _make_app(
            install_method="dmg", download_url="https://from-installomator.example/x.dmg"
        )
        detail = _make_detail(
            installomator={
                "label_name": "firefox",
                "label_url": "https://github.com/...",
                "raw": {
                    "name": "Firefox",
                    "type": "dmg",
                    "downloadURL": "https://from-installomator.example/x.dmg",
                    "expectedTeamID": "43AQ936H96",
                },
            },
        )

        result = build_installomator_label(app, detail)

        assert result.sources_used == ["installomator"]
        assert result.content["downloadURL"] == "https://from-installomator.example/x.dmg"
        assert result.content["expectedTeamID"] == "43AQ936H96"

    def test_installomator_shell_expression_url_falls_back_to_apps_row(self):
        """If Installomator's downloadURL is ``$(curl ...)``, we skip it."""
        app = _make_app(download_url="https://cask-derived.example/x.dmg")
        detail = _make_detail(
            installomator={
                "label_name": "firefox",
                "label_url": "https://github.com/...",
                "raw": {
                    "name": "Firefox",
                    "type": "dmg",
                    "downloadURL": "$(curl -fs ... | grep ...)",
                    "expectedTeamID": "43AQ936H96",
                },
            },
        )

        result = build_installomator_label(app, detail)

        # Should fall back to apps_row.download_url, not the shell expression
        assert not result.content["downloadURL"].startswith("$(")
        assert result.content["downloadURL"] == "https://cask-derived.example/x.dmg"

    def test_unknown_version_emits_warning(self):
        app = _make_app(current_version=None)
        detail = _make_detail(
            installomator={
                "label_name": "firefox",
                "label_url": "https://github.com/...",
                "raw": {
                    "name": "Firefox",
                    "type": "dmg",
                    "expectedTeamID": "43AQ936H96",
                },
            },
        )

        result = build_installomator_label(app, detail)

        assert "appNewVersion" not in result.content
        assert any("appNewVersion" in w for w in result.warnings)

    def test_unknown_type_falls_back_to_url_extension(self):
        app = _make_app(install_method=None)
        detail = _make_detail(
            homebrew_cask={
                "token": "x",
                "cask_json": {
                    "token": "x",
                    "name": ["X"],
                    "url": "https://example.com/x.pkg",
                    "version": "1.0",
                },
            },
        )

        result = build_installomator_label(app, detail)

        assert result.content["type"] == "pkg"
        assert any("Inferred install type" in w for w in result.warnings)

    def test_completely_unknown_type_defaults_with_warning(self):
        app = _make_app(install_method=None, download_url=None)
        detail = _make_detail(
            homebrew_cask={
                "token": "x",
                "cask_json": {"token": "x", "name": ["X"], "version": "1.0"},
            },
        )

        result = build_installomator_label(app, detail)

        assert result.content["type"] == "dmg"
        assert any("Could not determine install type" in w for w in result.warnings)

    def test_jai_only_app_uses_jai_fields_and_warns_about_team_id(self):
        """
        A JAI-only app produces a partial label: name, downloadURL, version
        from JAI, plus packageID from the (JAI-backfilled) apps row bundle_id.
        The team-ID warning still fires — JAI doesn't carry the vendor Team ID.
        """
        # apps row reflects what stitch produced: name + URL + version from JAI,
        # bundle_id backfilled from JAI (the precision-overlay / provider pattern).
        app = _make_app(
            slug="chatgpt-atlas",
            name="ChatGPT Atlas",
            install_method=None,
            download_url="https://vendor.example/ChatGPT-Atlas.pkg",
            current_version="1.0.0",
        )
        app.bundle_id = "com.openai.atlas"
        detail = _make_detail(jamf_app_installer=_JAI_EXTERNAL)

        result = build_installomator_label(app, detail)

        assert result.sources_used == ["jamf_app_installer"]
        content = result.content
        assert content["name"] == "ChatGPT Atlas"
        assert content["downloadURL"] == "https://vendor.example/ChatGPT-Atlas.pkg"
        assert content["appNewVersion"] == "1.0.0"
        assert content["packageID"] == "com.openai.atlas"
        # JAI cannot supply this — vendor Team ID still requires codesign.
        assert "expectedTeamID" not in content
        assert any("expectedTeamID" in w for w in result.warnings)

    def test_jai_jamf_hosted_url_not_used_for_downloadurl(self):
        """
        ``source = "Jamf"`` titles point at Jamf-repackaged installers signed by
        Jamf — those would fail Installomator's Team-ID validation. The builder
        must skip them and fall back to the apps row (which stitch likewise
        wouldn't have populated from JAI for the same reason).
        """
        app = _make_app(
            slug="some-app",
            name="Some App",
            install_method=None,
            download_url="https://apps-row-fallback.example/x.pkg",
            current_version="2.0",
        )
        jai = {
            **_JAI_EXTERNAL,
            "source": "Jamf",
            "download_url": "https://appinstallers-packages.services.jamfcloud.com/x.pkg",
        }
        detail = _make_detail(jamf_app_installer=jai)

        result = build_installomator_label(app, detail)

        # The Jamf-hosted JAI URL was ignored; fell through to the apps row.
        assert result.content["downloadURL"] == "https://apps-row-fallback.example/x.pkg"

    def test_packageid_added_when_bundle_id_set(self):
        """``packageID`` surfaces in content when the apps row has a bundle_id."""
        app = _make_app()
        app.bundle_id = "org.mozilla.firefox"
        detail = _make_detail(
            installomator={
                "label_name": "firefox",
                "label_url": "https://github.com/...",
                "raw": {
                    "name": "Firefox",
                    "type": "dmg",
                    "expectedTeamID": "43AQ936H96",
                },
            },
        )
        result = build_installomator_label(app, detail)
        assert result.content["packageID"] == "org.mozilla.firefox"

    def test_jai_title_used_for_name_when_cask_absent(self):
        """JAI title slots between Cask name and apps row in the name fallback chain."""
        app = _make_app(slug="x", name="Wrong Apps-Row Name")
        detail = _make_detail(jamf_app_installer=_JAI_EXTERNAL)
        result = build_installomator_label(app, detail)
        assert result.content["name"] == "ChatGPT Atlas"  # JAI title beat apps row

    def test_special_chars_in_name_survive_untouched(self):
        """JSON serialization handles escaping at the response layer — raw values pass through."""
        app = _make_app()
        detail = _make_detail(
            homebrew_cask={
                "token": "x",
                "cask_json": {
                    "token": "x",
                    "name": ['Quirky "Name" \\Test'],
                    "url": "https://example.com/x.dmg",
                    "version": "1.0",
                },
            },
        )

        result = build_installomator_label(app, detail)

        # Raw string in the dict; FastAPI/Pydantic will JSON-escape on serialization.
        assert result.content["name"] == 'Quirky "Name" \\Test'


@pytest.mark.parametrize(
    "url,expected_type",
    [
        ("https://example.com/foo.dmg", "dmg"),
        ("https://example.com/foo.pkg", "pkg"),
        ("https://example.com/foo.zip", "zip"),
        ("https://example.com/foo.tbz", "tbz"),
        ("https://example.com/foo.tar.bz2", "tbz"),
    ],
)
def test_url_extension_inference(url, expected_type):
    """The URL-extension fallback should recognize all the standard archive types."""
    from patcher_api.labels import _infer_type_from_url

    assert _infer_type_from_url(url) == expected_type


def test_url_extension_inference_returns_none_for_unrecognized():
    from patcher_api.labels import _infer_type_from_url

    assert _infer_type_from_url("https://example.com/foo.rpm") is None
    assert _infer_type_from_url(None) is None
