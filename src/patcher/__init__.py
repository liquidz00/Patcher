"""
Patcher — a Python library and CLI for Jamf Pro patch management reporting.

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

- :class:`PatcherClient` — the top-level library entry point. Holds
  ``jamf``, ``installomator``, and ``data`` collaborators as attributes.
- :class:`JamfClient` — Jamf Pro API client, available standalone for
  callers who only want the Jamf endpoints.
- :class:`InstallomatorClient` — Installomator label matching service.
  Naming pattern reserved for future siblings (Homebrew, AutoPkg, Jamf
  App Installer, the Patcher API service).
- Return shapes: :class:`PatchTitle`, :class:`PatchDevice` — useful for
  type-hinting your own code that consumes Patcher's responses.
- Exceptions: :class:`PatcherError`, :class:`APIResponseError`,
  :class:`CredentialError`, :class:`TokenError`, :class:`InstallomatorWarning`.

Submodules under :mod:`patcher.cli`, :mod:`patcher.core`, and
:mod:`patcher.client` remain importable for advanced use cases — for
example :class:`patcher.client.HTTPClient` for generic
httpx-with-truststore requests — but those paths are not part of the
stable public surface.

CLI-only objects (``Setup``, ``UIConfigManager``, ``PropertylistManager``,
``Animation``) are deliberately not re-exported here.
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
from .core.patcher_client import PatcherClient

__all__ = [
    "__version__",
    # Top-level library entry point
    "PatcherClient",
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
