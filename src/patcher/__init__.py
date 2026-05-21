"""
Patcher: a Python library and CLI for Jamf Pro patch management reporting.

For documentation, reference project docs at https://docs.patcherctl.dev/
"""

# configure keyring backend dynamically before importing anything
from ._platform import _configure_keyring

_configure_keyring()

from .__about__ import __version__
from .clients.installomator import InstallomatorClient
from .clients.jamf import JamfClient
from .clients.patcher_api import PatcherAPIClient
from .core.analyze import TitleFilter, TrendAnalysis
from .core.exceptions import (
    APIResponseError,
    CredentialError,
    InstallomatorWarning,
    PatcherError,
    TokenError,
)
from .core.models.patch import PatchDevice, PatchTitle
from .core.patcher_client import PatcherClient

__all__ = [
    "__version__",
    # Top-level library entry point
    "PatcherClient",
    # Per-service clients
    "JamfClient",
    "InstallomatorClient",
    "PatcherAPIClient",
    # Return shapes
    "PatchDevice",
    "PatchTitle",
    # Analysis surface (consumed by PatcherClient.analyze*)
    "TitleFilter",
    "TrendAnalysis",
    # Exceptions
    "APIResponseError",
    "CredentialError",
    "InstallomatorWarning",
    "PatcherError",
    "TokenError",
]
