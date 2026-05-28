"""Schema tests for the Jamf App Installers titles API models (real probe payloads)."""

from patcher_api.schemas.jamf_app_installers import JaiTitle, JaiTitlePage

# Verbatim detail payload from GET /api/v1/app-installers/titles/001 (dummy instance).
_DETAIL = {
    "id": "001",
    "bundleId": "com.adobe.acc.AdobeCreativeCloud",
    "titleName": "Adobe Creative Cloud",
    "publisher": "Adobe",
    "iconUrl": "https://appinstallers-packages.services.jamfcloud.com/icons/001.png",
    "version": "6.9.0.620",
    "installationPathShared": False,
    "sizeInBytes": 605512640,
    "minimumOsVersion": "10.15",
    "language": "",
    "availabilityDate": "2026-05-18T15:30:40Z",
    "packageSigningIdentity": "Developer ID Installer: JAMF Software (483DWKW443)",
    "installerPackageHashType": "MD5",
    "installerPackageHash": "71d0e42f74c484b98a31b83a80bd3b09",
    "shortVersion": "6.9.0.620",
    "architecture": "universal",
    "originalMediaSources": [
        {"hashType": "MD5", "hash": "7d7dce8153", "url": "https://ccmdls.adobe.com/arm64.dmg"},
        {"hashType": "MD5", "hash": "4ba0a4186d", "url": "https://ccmdls.adobe.com/osx10.dmg"},
    ],
    "originalTermsAndConditions": [],
    "mediaSourceType": "JAMF_SERVER",
    "launchDaemonIncluded": True,
    "notificationAvailable": True,
    "suppressAutoUpdate": False,
}

# The list endpoint returns a leaner item shape under {totalCount, results}.
_LIST_ITEM = {
    "id": "029",
    "bundleId": "com.adobe.Acrobat.Pro",
    "titleName": "Adobe Acrobat DC Continuous",
    "publisher": "Adobe",
    "iconUrl": "https://appinstallers-packages.services.jamfcloud.com/icons/029.png",
    "version": "26.001.21563",
    "installationPathShared": False,
}


def test_detail_payload_parses_fully():
    t = JaiTitle.model_validate(_DETAIL)
    assert t.id == "001"
    assert t.bundle_id == "com.adobe.acc.AdobeCreativeCloud"  # the stitch key
    assert t.title_name == "Adobe Creative Cloud"
    assert t.architecture == "universal"
    assert len(t.media_sources) == 2
    assert t.media_sources[0].url == "https://ccmdls.adobe.com/arm64.dmg"
    assert t.media_sources[0].hash_type == "MD5"
    # Install-mechanics signals are retained, not dropped.
    assert t.suppress_auto_update is False
    assert t.launch_daemon_included is True
    assert t.availability_date is not None
    assert t.size_in_bytes == 605512640


def test_lean_list_item_parses_with_optionals_defaulting():
    """The same model handles the list shape; missing detail fields default cleanly."""
    t = JaiTitle.model_validate(_LIST_ITEM)
    assert t.bundle_id == "com.adobe.Acrobat.Pro"
    assert t.media_sources == []
    assert t.suppress_auto_update is None  # absent in list shape


def test_title_page_parses():
    page = JaiTitlePage.model_validate({"totalCount": 152, "results": [_LIST_ITEM, _DETAIL]})
    assert page.total_count == 152
    assert [t.id for t in page.results] == ["029", "001"]


def test_construct_by_field_name_not_just_alias():
    """populate_by_name (via UpstreamModel) lets our own code build instances naturally."""
    t = JaiTitle(id="999", title_name="Test", bundle_id="com.test.app")
    assert t.title_name == "Test"
    assert t.bundle_id == "com.test.app"
