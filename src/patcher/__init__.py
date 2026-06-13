"""
Patcher: a Python library and CLI for Jamf Pro patch management reporting.

For documentation, reference project docs at https://docs.patcherctl.dev/

The public symbols below are imported lazily (PEP 562 ``__getattr__``): each is
pulled from its submodule only when first accessed. This keeps leaf imports like
``import patcher.catalog`` (the wire schemas the API server shares) from dragging
in pandas, keyring, and fpdf, which only the CLI/report paths need.
"""

from typing import TYPE_CHECKING

from .__about__ import __version__

if TYPE_CHECKING:
    # Eager imports for type checkers and IDEs only; never run at runtime.
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

# Public name -> the submodule it lives in, resolved on first access.
_LAZY_IMPORTS = {
    "PatcherClient": ".core.patcher_client",
    "JamfClient": ".clients.jamf",
    "InstallomatorClient": ".clients.installomator",
    "PatcherAPIClient": ".clients.patcher_api",
    "PatchDevice": ".core.models.patch",
    "PatchTitle": ".core.models.patch",
    "TitleFilter": ".core.analyze",
    "TrendAnalysis": ".core.analyze",
    "APIResponseError": ".core.exceptions",
    "CredentialError": ".core.exceptions",
    "InstallomatorWarning": ".core.exceptions",
    "PatcherError": ".core.exceptions",
    "TokenError": ".core.exceptions",
}

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


def __getattr__(name: str):
    module_path = _LAZY_IMPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(module_path, __name__), name)


def __dir__() -> list[str]:
    return sorted(__all__)
