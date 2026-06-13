"""Installomator label discovery and fetching (deprecated client)."""

import asyncio
import shutil
import warnings
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from ..catalog._fragment_parser import parse_fragment
from ..core.exceptions import APIResponseError, PatcherError
from ..core.logger import LogMe
from ..core.models.label import Label
from ..policy import INGEST_EXCLUDED_TEAM_IDS
from . import HTTPClient

# Parse Labels.txt up front to avoid the ~700-call fan-out the old approach did on first run.
_INSTALLOMATOR_RAW_BASE = (
    "https://raw.githubusercontent.com/Installomator/Installomator/refs/heads/main"
)
_LABELS_TXT_URL = f"{_INSTALLOMATOR_RAW_BASE}/Labels.txt"
_FRAGMENT_URL_TEMPLATE = f"{_INSTALLOMATOR_RAW_BASE}/fragments/labels/{{name}}.sh"

# Legacy on-disk label cache. Older versions persisted parsed fragments here with
# no expiration; the cache is gone and purge_legacy_disk_cache() sweeps leftovers.
_LEGACY_LABEL_CACHE = Path.home() / "Library/Application Support/Patcher/.labels"


class InstallomatorClient:
    """
    Discovers and fetches Installomator labels directly from upstream GitHub.

    .. deprecated::
       Prefer :class:`~patcher.core.patcher_client.PatcherClient` /
       :class:`~patcher.clients.patcher_api.PatcherAPIClient` for label and
       match data (set ``PATCHER_API_URL`` for self-hosted catalogs). This
       client will be removed in a future release.
    """

    def __init__(self, concurrency: int = 5, api: HTTPClient | None = None):
        """
        Wrapper around the `Installomator <https://github.com/Installomator/Installomator>`_ project (the macOS automated-installer script set).

        This class discovers and fetches Installomator labels. Discovery uses the lightweight ``Labels.txt`` file at the Installomator repo root; individual ``.sh`` fragments are fetched lazily.

        :param concurrency: Maximum concurrent requests for label fetches. Defaults to 5.
        :type concurrency: int
        :param api: HTTP client used for fetches against Installomator's GitHub.
            Defaults to a fresh :class:`~patcher.clients.HTTPClient`. No Jamf
            credentials required, so callers can use ``InstallomatorClient()``
            standalone to enumerate or fetch labels.
        :type api: :class:`~patcher.clients.HTTPClient` | None
        """
        warnings.warn(
            "InstallomatorClient is deprecated and will be removed in a future "
            "release. Use PatcherClient / PatcherAPIClient for label and match "
            "data (set PATCHER_API_URL for self-hosted catalogs).",
            DeprecationWarning,
            stacklevel=2,
        )
        self.log = LogMe(self.__class__.__name__)
        self.api = api if api is not None else HTTPClient(max_concurrency=concurrency)

        # Session-scoped caches: parsed label names + fetched Label objects by name.
        self._available_names: set[str] | None = None
        self._labels_by_name: dict[str, Label] = {}

    @staticmethod
    def purge_legacy_disk_cache() -> bool:
        """
        Remove the legacy on-disk Installomator label cache if present.

        Older versions persisted parsed label fragments under
        ``~/Library/Application Support/Patcher/.labels`` with no expiration or
        invalidation. That cache is gone; this best-effort sweep deletes any
        leftover directory so stale fragments don't linger. Safe to call when
        the directory is absent.

        :return: True if a directory was removed, False if there was nothing to
            remove or removal failed (failures are logged, not raised).
        :rtype: bool
        """
        if not _LEGACY_LABEL_CACHE.exists():
            return False
        log = LogMe(InstallomatorClient.__name__)
        try:
            shutil.rmtree(_LEGACY_LABEL_CACHE)
            log.info(f"Removed legacy Installomator label cache at {_LEGACY_LABEL_CACHE}")
            return True
        except OSError as e:
            log.warning(f"Could not remove legacy label cache {_LEGACY_LABEL_CACHE}: {e}")
            return False

    def _build_label_from_content(self, content: str, script_name: str) -> Label | None:
        """
        Parse a fragment's raw .sh content into a ``Label`` object.

        Returns ``None`` if the fragment's expected Team ID is in
        :data:`~patcher.policy.INGEST_EXCLUDED_TEAM_IDS` or if Pydantic validation fails.
        """
        fragment_dict = parse_fragment(content)

        # A key assigned more than once parses to a list; scalar fields take the first (matches the API projection).
        fragment_dict = {
            key: (value[0] if isinstance(value, list) and value else value)
            for key, value in fragment_dict.items()
        }

        expected_team_id = fragment_dict.get("expectedTeamID")
        if expected_team_id in INGEST_EXCLUDED_TEAM_IDS:
            self.log.warning(f"Skipping label {script_name} (ignored Team ID: {expected_team_id})")
            return None

        try:
            return Label.from_dict(fragment_dict, installomator_label=script_name)
        except ValidationError as e:
            self.log.warning(
                f"Skipping invalid Installomator label: {script_name} due to validation error: {e}"
            )
            return None

    async def list_available_labels(self) -> set[str]:
        """
        Return the set of every label name currently available in Installomator.

        Fetches and parses ``_LABELS_TXT_URL``. The result is cached on the instance for the session; subsequent calls do not re-fetch.

        :return: A set of label script names (e.g. ``{"googlechrome", "1password8", ...}``).
        :rtype: set[str]
        :raises PatcherError: If the labels file cannot be fetched.
        """
        if self._available_names is not None:
            return self._available_names

        self.log.debug(f"Fetching Installomator Labels.txt from {_LABELS_TXT_URL}")
        try:
            content = await self.api.fetch_text(_LABELS_TXT_URL)
        except APIResponseError as e:
            raise PatcherError("Unable to retrieve Installomator Labels.txt", error_msg=str(e))

        # One name per line; skip blanks/comments and lowercase to match the matching pipeline.
        names = {
            line.strip().lower()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        self._available_names = names
        self.log.info(f"Discovered {len(names)} Installomator labels.")
        return names

    async def get_label(self, name: str) -> Label | None:
        """
        Fetch and parse a single Installomator label by script name.

        Lookup order:

        1. Instance (session) cache (``self._labels_by_name``)
        2. HTTP fetch from ``_FRAGMENT_URL_TEMPLATE``

        :param name: The Installomator script name (e.g. ``"googlechrome"``).
            Case-insensitive; normalized to lowercase before lookup.
        :type name: str
        :return: The constructed ``Label`` object, or ``None`` if the fragment
            cannot be fetched, is ignored by Team ID, or fails validation.
        :rtype: :class:`~patcher.core.models.label.Label` | None
        """
        key = name.lower()
        if key in self._labels_by_name:
            return self._labels_by_name[key]

        # fetch_text raises on non-2xx, so one broken label logs + returns None instead of killing the batch.
        url = _FRAGMENT_URL_TEMPLATE.format(name=key)
        self.log.debug(f"Fetching Installomator fragment from {url}")
        try:
            content = await self.api.fetch_text(url)
        except APIResponseError as e:
            self.log.warning(f"Failed to fetch Installomator fragment for '{name}': {e}")
            return None

        if not content:
            return None

        label = self._build_label_from_content(content, key)
        if label is not None:
            self._labels_by_name[key] = label
        return label

    async def get_labels(self, names: Iterable[str] | None = None) -> list[Label]:
        """
        Fetch and parse multiple Installomator labels in parallel.

        :param names: Specific label script names to fetch. If ``None`` (the
            default), fetches **every** label listed in ``_LABELS_TXT_URL``,
            typically ~700 HTTP calls on first run and served from disk cache
            on subsequent runs. Prefer passing a concrete name list when you
            know what you need.
        :type names: Iterable[str] | None
        :return: List of successfully parsed ``Label`` objects. Labels that
            fail to fetch, hit an ignored Team ID, or fail validation are
            silently omitted (warnings are logged).
        :rtype: list[:class:`~patcher.core.models.label.Label`]
        """
        if names is None:
            names_iter = await self.list_available_labels()
        else:
            names_iter = {n.lower() for n in names}

        if not names_iter:
            return []

        tasks = [self.get_label(name) for name in names_iter]
        results = await asyncio.gather(*tasks)
        return [label for label in results if label is not None]
