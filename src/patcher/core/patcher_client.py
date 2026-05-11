"""High-level facade for Patcher's library use.

Composes the per-service clients (:class:`JamfClient`,
:class:`InstallomatorClient`), data layer (:class:`DataManager`), and
report orchestration helpers (:class:`ReportManager`) into a single object
library callers instantiate. CLI users construct the same object via the
existing ``Setup`` flow, which populates a :class:`ConfigManager` and
hands it to ``PatcherClient`` through the ``config=`` argument.

For raw, lower-level access without the facade, see
:class:`patcher.client.jamf.JamfClient` (Jamf API directly) and
:class:`patcher.client.HTTPClient` (generic httpx with truststore).
"""

from ..client.jamf import JamfClient
from .config_manager import ConfigManager
from .data_manager import DataManager
from .exceptions import PatcherError
from .installomator import InstallomatorClient
from .logger import LogMe
from .models.ui import UIDefaults


class PatcherClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        server: str | None = None,
        *,
        config: ConfigManager | None = None,
        concurrency: int = 5,
        disable_cache: bool = False,
        debug: bool = False,
        enable_installomator: bool = True,
        ui_config: dict | None = None,
    ):
        """
        Construct a Patcher facade with all collaborators wired up.

        Two construction paths:

        - **Direct credentials** (library use)::

            from patcher import PatcherClient

            patcher = PatcherClient(
                client_id="...",
                client_secret="...",
                server="https://myorg.jamfcloud.com",
            )
            summaries = await patcher.jamf.get_summaries(
                await patcher.jamf.get_policies()
            )

          Builds an in-memory :class:`ConfigManager` internally — no keyring
          backend required, no plist mutation, no disk I/O on construction.

        - **Existing ConfigManager** (CLI use)::

            patcher = PatcherClient(config=existing_config_manager, ...)

          For the CLI path where setup has already populated keyring.

        Exactly one of ``(client_id + client_secret + server)`` or
        ``config`` must be provided.

        :param client_id: Jamf Pro API client ID.
        :type client_id: str | None
        :param client_secret: Jamf Pro API client secret.
        :type client_secret: str | None
        :param server: Jamf Pro instance URL (e.g. ``https://myorg.jamfcloud.com``).
        :type server: str | None
        :param config: Existing ``ConfigManager`` instance — mutually
            exclusive with the credentials arguments.
        :type config: :class:`~patcher.core.config_manager.ConfigManager` | None
        :param concurrency: Maximum concurrent API requests. Defaults to 5,
            the recommended ceiling per the `Jamf Developer Guide
            <https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices>`_.
        :type concurrency: int
        :param disable_cache: If True, :class:`DataManager` skips on-disk
            patch-data caching.
        :type disable_cache: bool
        :param debug: Enables debug-mode handling in collaborators (notably
            disables the spinner animation when set in the CLI path).
        :type debug: bool
        :param enable_installomator: If False, :attr:`installomator` is
            ``None`` and Installomator label matching is skipped.
        :type enable_installomator: bool
        :param ui_config: Optional dict of UI settings (header text,
            footer, font paths, header color, etc.) for PDF/HTML report
            styling. Defaults to :class:`UIDefaults` values.
        :type ui_config: dict | None
        :raises PatcherError: If neither credentials nor ``config`` are
            provided.
        """
        self.log = LogMe(self.__class__.__name__)

        if config is None:
            if not (client_id and client_secret and server):
                raise PatcherError(
                    "PatcherClient requires either `config=` or all three of "
                    "`client_id`, `client_secret`, and `server`.",
                )
            config = ConfigManager(
                in_memory_credentials={
                    "CLIENT_ID": client_id,
                    "CLIENT_SECRET": client_secret,
                    "URL": server,
                }
            )

        self._config = config
        self.debug = debug
        self.jamf = JamfClient(config=config, concurrency=concurrency)
        self.data = DataManager(disable_cache=disable_cache)
        self.installomator = (
            InstallomatorClient(concurrency=concurrency, api=self.jamf)
            if enable_installomator
            else None
        )
        self.ui_config = ui_config if ui_config is not None else UIDefaults().model_dump()
