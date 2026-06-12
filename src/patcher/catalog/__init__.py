"""
Shared catalog domain used by both the library and the API.

Wire schemas (and later the fragment parser) shared across the package and the
API server. The schemas are re-exported here so both sides import the one
definition directly: ``from patcher.catalog import App``.
"""

from .schemas import (
    App,
    AppSources,
    AutopkgRecipeEntry,
    AutopkgSource,
    DriftEntry,
    DriftResponse,
    GeneratedLabel,
    HomebrewCaskSource,
    InstallMethod,
    InstallomatorSource,
    JamfAppInstallerSource,
    SourceVersion,
)

__all__ = [
    "App",
    "AppSources",
    "AutopkgRecipeEntry",
    "AutopkgSource",
    "DriftEntry",
    "DriftResponse",
    "GeneratedLabel",
    "HomebrewCaskSource",
    "InstallMethod",
    "InstallomatorSource",
    "JamfAppInstallerSource",
    "SourceVersion",
]
