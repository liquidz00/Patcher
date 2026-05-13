"""
In-memory seed data for the Patcher API.

Stands in for the SQLite database during the vertical-slice phase. When
persistence lands, this module is replaced (or repurposed as a seeding script
that populates the DB on first run).
"""

from datetime import date

from patcher_api.schemas.app import App, InstallMethod
from patcher_api.schemas.sources import (
    AppSources,
    HomebrewCaskSource,
    InstallomatorSource,
)

SEED_APPS: list[App] = [
    App(
        slug="firefox",
        bundle_id="com.mozilla.firefox",
        name="Firefox",
        vendor="Mozilla",
        current_version="121.0",
        latest_release_date=date(2023, 12, 19),
        download_url="https://download.mozilla.org/?product=firefox-pkg-latest-ssl&os=osx&lang=en-US",
        install_method=InstallMethod.PKG,
        sources=["installomator", "homebrew_cask"],
    ),
    App(
        slug="google-chrome",
        bundle_id="com.google.Chrome",
        name="Google Chrome",
        vendor="Google",
        current_version="120.0.6099.129",
        latest_release_date=date(2023, 12, 12),
        download_url="https://dl.google.com/chrome/mac/stable/GGRO/googlechrome.pkg",
        install_method=InstallMethod.PKG,
        sources=["installomator", "homebrew_cask"],
    ),
    App(
        slug="slack",
        bundle_id="com.tinyspeck.slackmacgap",
        name="Slack",
        vendor="Slack",
        current_version="4.36.140",
        latest_release_date=date(2024, 2, 28),
        download_url="https://downloads.slack-edge.com/releases/macos/4.36.140/prod/universal/Slack-4.36.140-macOS.dmg",
        install_method=InstallMethod.DMG,
        sources=["installomator"],
    ),
    App(
        slug="zoom",
        bundle_id="us.zoom.xos",
        name="Zoom",
        vendor="Zoom",
        current_version="5.17.5",
        latest_release_date=date(2024, 2, 12),
        download_url="https://zoom.us/client/latest/ZoomInstallerIT.pkg",
        install_method=InstallMethod.PKG,
        sources=["installomator", "homebrew_cask"],
    ),
    App(
        slug="vscode",
        bundle_id="com.microsoft.VSCode",
        name="Visual Studio Code",
        vendor="Microsoft",
        current_version="1.87.0",
        latest_release_date=date(2024, 3, 5),
        download_url="https://code.visualstudio.com/sha/download?build=stable&os=darwin-universal",
        install_method=InstallMethod.ZIP,
        sources=["installomator", "homebrew_cask"],
    ),
    App(
        slug="microsoft-edge",
        bundle_id="com.microsoft.edgemac",
        name="Microsoft Edge",
        vendor="Microsoft",
        current_version="122.0.2365.59",
        latest_release_date=date(2024, 3, 1),
        download_url="https://go.microsoft.com/fwlink/?linkid=2069148",
        install_method=InstallMethod.PKG,
        sources=["homebrew_cask"],
    ),
]


SEED_SOURCES: dict[str, AppSources] = {
    "firefox": AppSources(
        installomator=InstallomatorSource(
            label_name="firefoxpkg",
            label_url="https://github.com/Installomator/Installomator/blob/main/fragments/labels/firefoxpkg.sh",
            raw={
                "name": "Firefox",
                "type": "pkg",
                "packageID": "org.mozilla.firefox",
                "downloadURL": "https://download.mozilla.org/?product=firefox-pkg-latest-ssl&os=osx&lang=en-US",
                "appNewVersion": "121.0",
                "expectedTeamID": "43AQ936H96",
                "blockingProcesses": ["firefox"],
            },
        ),
        homebrew_cask=HomebrewCaskSource(
            token="firefox",
            cask_json={
                "token": "firefox",
                "name": ["Mozilla Firefox"],
                "desc": "Web browser",
                "homepage": "https://www.mozilla.org/firefox/",
                "url": "https://download-installer.cdn.mozilla.net/pub/firefox/releases/121.0/mac/en-US/Firefox%20121.0.dmg",
                "version": "121.0",
                "sha256": "no_check",
                "auto_updates": True,
                "depends_on": {"macos": ">= :el_capitan"},
                "artifacts": [{"app": ["Firefox.app"]}],
            },
        ),
    ),
    "google-chrome": AppSources(
        installomator=InstallomatorSource(
            label_name="googlechromepkg",
            label_url="https://github.com/Installomator/Installomator/blob/main/fragments/labels/googlechromepkg.sh",
            raw={
                "name": "Google Chrome",
                "type": "pkg",
                "packageID": "com.google.Chrome",
                "downloadURL": "https://dl.google.com/chrome/mac/stable/GGRO/googlechrome.pkg",
                "expectedTeamID": "EQHXZ8M8AV",
                "blockingProcesses": ["Google Chrome"],
                "updateTool": "/Library/Google/GoogleSoftwareUpdate/GoogleSoftwareUpdate.bundle/Contents/Resources/GoogleSoftwareUpdateAgent.app/Contents/MacOS/GoogleSoftwareUpdateAgent",
                "updateToolArguments": ["-runMode", "oneshot", "-userInitiated", "YES"],
            },
        ),
        homebrew_cask=HomebrewCaskSource(
            token="google-chrome",
            cask_json={
                "token": "google-chrome",
                "name": ["Google Chrome"],
                "desc": "Web browser",
                "homepage": "https://www.google.com/chrome/",
                "url": "https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg",
                "version": "120.0.6099.129",
                "sha256": "no_check",
                "auto_updates": True,
                "artifacts": [{"app": ["Google Chrome.app"]}],
            },
        ),
    ),
    "microsoft-edge": AppSources(
        homebrew_cask=HomebrewCaskSource(
            token="microsoft-edge",
            cask_json={
                "token": "microsoft-edge",
                "name": ["Microsoft Edge"],
                "desc": "Web browser",
                "homepage": "https://www.microsoft.com/edge",
                "url": "https://officecdnmac.microsoft.com/pr/C1297A47-86C4-4C1F-97FA-950631F94777/MacAutoupdate/MicrosoftEdge-122.0.2365.59.pkg",
                "version": "122.0.2365.59",
                "sha256": "no_check",
                "auto_updates": True,
                "artifacts": [{"app": ["Microsoft Edge.app"]}],
            },
        ),
    ),
}
