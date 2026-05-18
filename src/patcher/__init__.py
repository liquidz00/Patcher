"""
Patcher: a Python library and CLI for Jamf Pro patch management reporting.

For CLI usage, install with ``pip install patcherctl`` and run ``patcherctl --help``.

For library usage, the headline entry point is :class:`PatcherClient`:

.. code-block:: python

    from patcher import PatcherClient

    patcher = PatcherClient(
        client_id="...",
        client_secret="...",
        server="https://myorg.jamfcloud.com",
    )

    # Talk to Jamf:
    summaries = await patcher.jamf.get_summaries(
        await patcher.jamf.get_policies()
    )

    # Match against Installomator labels:
    await patcher.installomator.match(summaries)

    # Export to disk:
    await patcher.data.export(
        patch_titles=summaries,
        output_dir=Path("~/reports").expanduser(),
        formats={"pdf", "html"},
        ...
    )

**Public surface:**

- :class:`PatcherClient`: the top-level library entry point. Holds
  ``jamf``, ``installomator``, and ``data`` collaborators as attributes.
- :class:`JamfClient`: Jamf Pro API client, available standalone for
  callers who only want the Jamf endpoints.
- :class:`InstallomatorClient`: Installomator label matching service.
- :class:`PatcherAPIClient`: client for the public Patcher API catalog
  (https://api.patcherctl.dev). Useful standalone for scripting against
  stitched app metadata.
- Return shapes: :class:`PatchTitle`, :class:`PatchDevice`. Useful for
  type-hinting your own code that consumes Patcher's responses.
- Exceptions: :class:`PatcherError`, :class:`APIResponseError`,
  :class:`CredentialError`, :class:`TokenError`, :class:`InstallomatorWarning`.

Submodules under :mod:`patcher.cli`, :mod:`patcher.core`, and
:mod:`patcher.clients` remain importable for advanced use cases (for
example :class:`patcher.clients.HTTPClient` for generic
httpx-with-truststore requests), but those paths are not part of the
stable public surface.

CLI-only objects (``Setup``, ``UIConfigManager``, ``PropertylistManager``,
``Animation``) are deliberately not re-exported here.
"""

from .__about__ import __version__
from .clients.installomator import InstallomatorClient
from .clients.jamf import JamfClient
from .clients.patcher_api import PatcherAPIClient
from .core.analyze import FilterCriteria, TrendCriteria
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
    # Analysis criteria enums (consumed by PatcherClient.analyze)
    "FilterCriteria",
    "TrendCriteria",
    # Exceptions
    "APIResponseError",
    "CredentialError",
    "InstallomatorWarning",
    "PatcherError",
    "TokenError",
]
