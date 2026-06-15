"""
Catalog policy shared across the library, CLI, and API.

Each constant is consumed by a different layer and is intentionally
independent: ``INGEST_EXCLUDED_TEAM_IDS`` filters Installomator fragments at
ingest, ``IGNORED_TITLES`` is the client matcher's Jamf-title skip list, and
``CURATED_BUNDLE_IDS`` seeds bundle_ids the catalog stitch needs to attach Jamf
App Installers to install sources that carry none, and ``IGNORED_EXPORT_COLUMNS``
lists the internal columns stripped from the rendered PDF/Excel/HTML reports.
"""

#: Apple Developer Team IDs dropped while parsing Installomator fragments. These are labels with broken or non-standard data (for example, ``lcadvancedvpnclient``, and the ``zulujdk*`` labels whose versioning relies on HTML scraping). Excluding them at ingest keeps the bad records out of the catalog entirely.
INGEST_EXCLUDED_TEAM_IDS: frozenset[str] = frozenset({
    "Frydendal",  # Non-standard team value
    "Media",  # Non-standard team value
    "LL3KBL2M3A",  # lcadvancedvpnclient (broken data)
    "TDTHCUPYFR",  # zulujdk* labels (problematic versioning nuances, web scraping)
})

#: The client matcher's skip list of Jamf patch-title names. A title here is never matched against the catalog, either because it is managed out-of-band (Adobe via the Admin Console), updated by its own mechanism (Jamf, Apple), or no longer supported. This is distinct from the user-configurable ``ignored_titles`` plist setting, which is a per-install preference layered on top.
IGNORED_TITLES: list[str] = [
    "Apple macOS *",
    "Oracle Java SE *",
    "Eclipse Temurin *",
    "Apple Safari",
    "Apple Xcode",
    "Microsoft Visual Studio",  # Support deprecated
    "Adobe *",  # managed out-of-band via the Adobe Admin Console
    "Jamf *",  # updated by Jamf's own mechanisms
]

#: Some install sources carry no bundle identifier, so Jamf App Installers titles cannot attach to them automatically. Each entry supplies the authoritative ``bundleId`` (taken from the App Installers titles API) so the stitch can bridge the gap for high-value apps like Zoom, Docker, and OBS.
CURATED_BUNDLE_IDS: dict[str, str] = {
    "aspera": "com.ibm.software.aspera.desktop",
    "bbedit": "com.barebones.bbedit",
    "charles": "com.xk72.Charles",
    "claudedesktop": "com.anthropic.claudefordesktop",
    "cursorai": "com.todesktop.230313mzl4w4u92",
    "dbeaverce": "org.jkiss.dbeaver.core.product",
    "docker": "com.docker.docker",
    "farrago": "com.rogueamoeba.farrago",
    "filemakerpro": "com.filemaker.client.pro12",
    "intellij-idea-ce": "com.jetbrains.intellij.ce",
    "kiro": "dev.kiro.desktop",
    "microsoftcompanyportal": "com.microsoft.CompanyPortalMac",
    "microsoftwindowsapp": "com.microsoft.rdc.macos",
    "musescore": "org.musescore.MuseScore",
    "nextcloud": "com.nextcloud.desktopclient",
    "obs": "com.obsproject.obs-studio",
    "pycharm-ce": "com.jetbrains.pycharm.ce",
    "realvncviewer": "com.realvnc.vncviewer",
    "sassafraskeyaccess": "com.sassafras.KeyAccess",
    "suspiciouspackage": "com.mothersruin.SuspiciousPackageApp",
    "teamviewer-host": "com.teamviewer.TeamViewerHost",
    "teamviewer-quickjoin": "com.teamviewer.TeamViewerQJ",
    "windsurf": "com.exafunction.windsurf",
    "zoom": "us.zoom.xos",
}

#: The internal columns dropped from the rendered reports. See :ref:`the exported field policy <exported-field-policy>` in the usage docs for more.
IGNORED_EXPORT_COLUMNS: list[str] = [
    "sources",
    "title_id",
    "name_id"
]
