"""
Catalog policy shared across the library, CLI, and API.

Each constant is consumed by a different layer and is intentionally
independent: ``INGEST_EXCLUDED_TEAM_IDS`` filters Installomator fragments at
ingest, ``IGNORED_TITLES`` is the client matcher's Jamf-title skip list, and
``CURATED_BUNDLE_IDS`` seeds bundle_ids the catalog stitch needs to attach Jamf
App Installers to install sources that carry none.
"""

# LL3KBL2M3A is lcadvancedvpnclient (broken data); Frydendal/Media are non-standard team values
# TDTHCUPYFR is zulujdk* labels which are problematic due to versioning nuances and HTML scraping
INGEST_EXCLUDED_TEAM_IDS: frozenset[str] = frozenset(
    {"Frydendal", "Media", "LL3KBL2M3A", "TDTHCUPYFR"}
)

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

# Apps whose install source has no bundle_id but Jamf's catalog does; values are
# the authoritative bundleId from the App Installers titles API. Keyed by slug.
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
