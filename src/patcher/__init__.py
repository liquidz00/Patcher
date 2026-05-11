"""Patcher — a Python library and CLI for Jamf Pro patch management reporting.

For CLI usage, install with ``pip install patcherctl`` and run ``patcherctl --help``.

For library usage, the headline entry point is :class:`JamfClient`:

.. code-block:: python

    from patcher import JamfClient

    client = JamfClient.from_credentials(
        client_id="...",
        client_secret="...",
        server="https://myorg.jamfcloud.com",
    )
    summaries = await client.get_summaries(await client.get_policies())

**Public surface:**

- HTTP clients per service: :class:`JamfClient` (Jamf Pro). Future per-service
  clients (Homebrew, AutoPkg, Jamf App Installer, the Patcher API itself)
  will land here too.
- :class:`InstallomatorClient` — InstallomatorClient label matching against patch
  titles. Same naming pattern; expect siblings for other patching ecosystems
  in future releases.
- Return shapes: :class:`PatchTitle`, :class:`PatchDevice` — useful for
  type-hinting your own code that consumes Patcher's responses.
- Exceptions: :class:`PatcherError`, :class:`APIResponseError`,
  :class:`CredentialError`, :class:`TokenError`, :class:`InstallomatorWarning`.

Submodules under :mod:`patcher.cli`, :mod:`patcher.core`, and
:mod:`patcher.client` remain importable for advanced use cases (e.g.,
:class:`patcher.client.HTTPClient` for generic httpx-with-truststore
requests, :class:`patcher.core.data_manager.DataManager` for raw export
workflows), but those paths are not part of the stable public surface.

CLI-only objects (``Setup``, ``SetupError``, ``Animation``,
``UIConfigManager``, ``PropertylistManager``) are deliberately not
re-exported here — library callers go through :class:`JamfClient` and
its collaborators instead.
"""

from .__about__ import __version__
from .client.jamf import JamfClient
from .core.exceptions import (
    APIResponseError,
    CredentialError,
    InstallomatorWarning,
    PatcherError,
    TokenError,
)
from .core.installomator import InstallomatorClient
from .core.models.patch import PatchDevice, PatchTitle

__all__ = [
    "__version__",
    # Per-service clients
    "JamfClient",
    "InstallomatorClient",
    # Return shapes
    "PatchDevice",
    "PatchTitle",
    # Exceptions
    "APIResponseError",
    "CredentialError",
    "InstallomatorWarning",
    "PatcherError",
    "TokenError",
]
