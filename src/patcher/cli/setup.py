from enum import Enum
from pathlib import Path

import asyncclick as click
from PIL import Image

from ..cli.ui_manager import UIConfigManager
from ..clients import HTTPClient
from ..clients.token_manager import TokenManager
from ..core.config_manager import ConfigManager
from ..core.exceptions import APIResponseError, PatcherError, SetupError, TokenError
from ..core.logger import LogMe
from ..core.models.token import AccessToken
from ..core.models.ui import UIConfigKeys, UIDefaults
from ..core.plist_manager import PropertylistManager
from .animation import Animation

# Welcome messages
GREET = "Thanks for downloading Patcher!\n"
WELCOME = """It looks like this is your first time using the tool. We will guide you through the initial setup to get you started.

The setup assistant will prompt you to choose your setup method--Standard is the automated setup which will prompt for your Jamf URL, your Jamf Pro username and your Jamf Pro password. Patcher ONLY uses this information to create the necessary API role and client on your behalf, your credentials are not stored whatsoever. Once generated, these client credentials (and generated bearer token) can be found in your keychain. The SSO setup will prompt for a client ID and client secret of an API Client that has already been created.

You will be prompted to enter in the header and footer text for PDF reports, along with optional custom fonts and branding logo. These can be configured later by modifying the corresponding keys in the com.liquidzoo.patcher.plist file in Patcher's Application Support directory stored in the user library.

"""
DOC = "For more information, visit the project documentation: https://docs.patcherctl.dev\n"


class SetupType(str, Enum):
    """
    Defines the method of setup used for configuring Patcher.

    - ``STANDARD``: Prompts for Jamf Pro username/password and creates an API client.
    - ``SSO``: Prompts for an existing API client ID and secret.
    """

    STANDARD = "standard"
    SSO = "sso"


class Setup:
    def __init__(
        self,
        config: ConfigManager,
        ui_config: UIConfigManager,
        plist_manager: PropertylistManager,
    ):
        """
        Handles the initial setup process for the Patcher CLI tool.

        This class guides users through configuring the necessary components to integrate
        with their Jamf environment. The setup includes creating API roles, clients, and configuring
        user interface settings for PDF reports.

        :param config: Manages application configuration, including credential storage.
        :type config: :class:`~patcher.core.config_manager.ConfigManager`
        :param ui_config: Handles UI-related configurations for the setup process.
        :type ui_config: :class:`~patcher.cli.ui_manager.UIConfigManager`
        :param plist_manager: Handles read/write operations to project property list.
        :type plist_manager: :class:`~patcher.core.plist_manager.PropertylistManager`
        """
        self.config = config
        self.ui_config = ui_config
        self.plist_manager = plist_manager
        self.log = LogMe(self.__class__.__name__)
        self.animator = Animation()
        self._completed = None

    @property
    def completed(self) -> bool:
        """
        Indicates whether the setup process has been completed.

        :return: True if setup has been completed, False otherwise.
        :rtype: bool
        """
        if self._completed is None:
            self.log.debug("Checking setup completion status.")
            self._completed = self.plist_manager.get("setup_completed") or False
        return self._completed

    @staticmethod
    def _greet() -> None:
        """Displays the greeting and welcome messages."""
        click.echo(click.style(GREET, fg="cyan", bold=True))
        click.echo(click.style(WELCOME), nl=False)
        click.echo(click.style(DOC, fg="bright_magenta", bold=True))

    def _mark_completion(self, value: bool = False) -> None:
        """Update the ``setup_completed`` plist key and the in-memory cache."""
        self.plist_manager.set("setup_completed", value)
        self._completed = value

    def _get_creds(self, include_token: bool = False) -> dict:
        """Retrieves all stored credentials from keychain."""
        keys = ["URL", "CLIENT_ID", "CLIENT_SECRET"]
        if include_token:
            keys.extend(["TOKEN", "TOKEN_EXPIRATION"])
        return {key: self.config.get_credential(key) for key in keys}

    def _save_creds(self, creds: dict) -> None:
        """Save gathered credentials to keychain."""
        for key, value in creds.items():
            self.config.set_credential(key, value)

    async def prompt_credentials(self, setup_type: SetupType) -> dict:
        """
        Prompt for credentials based on the credential type.

        :param setup_type: The ``SetupType`` of credentials to prompt for.
        :type setup_type: SetupType
        :return: The credentials in dictionary form.
        :rtype: dict
        """
        self.log.info(f"Prompting user for {setup_type.value} credentials.")
        if setup_type == SetupType.STANDARD:
            return {
                "URL": await click.prompt("Enter your Jamf Pro URL"),
                "USERNAME": await click.prompt("Enter your Jamf Pro username"),
                "PASSWORD": await click.prompt("Enter your Jamf Pro password", hide_input=True),
            }
        elif setup_type == SetupType.SSO:
            return {
                "URL": await click.prompt("Enter your Jamf Pro URL"),
                "CLIENT_ID": await click.prompt("Enter your API Client ID"),
                "CLIENT_SECRET": await click.prompt("Enter your API Client Secret"),
            }

    async def prompt_ui_settings(self) -> None:
        """
        Drive the interactive UI configuration prompts (header/footer text,
        font, logo, header color) and persist them via the
        :class:`~patcher.cli.ui_manager.UIConfigManager`. Triggers font
        downloads on first run.

        Replaces the legacy ``UIConfigManager.setup_ui`` method, moved to the
        CLI layer so the core UI config object stays free of ``asyncclick``
        and ``PIL`` dependencies for library callers.
        """
        self.log.debug("Prompting user for UI setup.")
        defaults = UIDefaults()
        self.ui_config._download_fonts()

        header_text = await click.prompt(
            "Enter Header Text for PDF reports",
            default=self.ui_config.config.get(UIConfigKeys.HEADER.value, defaults.header_text),
            show_default=True,
        )
        footer_text = await click.prompt(
            "Enter Footer Text for PDF reports",
            default=self.ui_config.config.get(UIConfigKeys.FOOTER.value, defaults.footer_text),
            show_default=True,
        )

        settings = {
            UIConfigKeys.HEADER.value: header_text,
            UIConfigKeys.FOOTER.value: footer_text,
            UIConfigKeys.FONT_NAME.value: "Assistant",
            UIConfigKeys.REG_FONT_PATH.value: str(self.ui_config._get_font_paths()["regular"]),
            UIConfigKeys.BOLD_FONT_PATH.value: str(self.ui_config._get_font_paths()["bold"]),
            UIConfigKeys.LOGO_PATH.value: "",
        }

        if click.confirm("Would you like to use a custom font?", default=False):
            settings.update(await self.prompt_font_config())

        if click.confirm(
            "Would you like to use a custom logo in your exported PDF reports?", default=False
        ):
            settings[UIConfigKeys.LOGO_PATH.value] = await self.prompt_logo_config()

        if click.confirm(
            "Would you like to use a custom header color in your exported HTML reports?",
            default=False,
        ):
            header_color = str(await click.prompt("Enter header color value (Hex format)"))
            if not header_color.startswith("#"):
                header_color = f"#{header_color}"
            settings[UIConfigKeys.HEADER_COLOR.value] = header_color

        self.ui_config.config = settings

    async def prompt_font_config(self) -> dict[str, str]:
        """
        Prompt for custom font paths and copy them into Patcher's font
        directory.

        :return: A dictionary containing the font name, regular font path,
            and bold font path.
        :rtype: dict[str, str]
        """
        font_name = await click.prompt("Enter custom font name", default="CustomFont")
        regular_src = Path(await click.prompt("Enter the path to the regular font file"))
        bold_src = Path(await click.prompt("Enter the path to the bold font file"))

        font_paths = self.ui_config._get_font_paths()
        regular_dest, bold_dest = font_paths["regular"], font_paths["bold"]
        self.ui_config._copy_file(regular_src, regular_dest)
        self.ui_config._copy_file(bold_src, bold_dest)

        return {
            UIConfigKeys.FONT_NAME.value: font_name,
            UIConfigKeys.REG_FONT_PATH.value: str(regular_dest),
            UIConfigKeys.BOLD_FONT_PATH.value: str(bold_dest),
        }

    async def prompt_logo_config(self) -> str:
        """
        Prompt for a logo file path, validate it as an image, and copy it
        into Patcher's Application Support directory.

        :return: The path to the saved logo file.
        :rtype: str
        :raises SetupError: If the provided logo path does not exist.
        :raises PatcherError: If the file is not a valid image, or copying fails.
        """
        logo_src = Path(await click.prompt("Enter the path to the logo file"))
        if not logo_src.exists():
            raise SetupError(
                "The specified logo path does not exist, please check the path and try again.",
                path=logo_src,
            )

        try:
            with Image.open(logo_src) as img:
                img.verify()
            self.log.info(f"Logo file {logo_src} validated successfully.")
        except (IOError, Image.UnidentifiedImageError) as e:
            self.log.error(f"Image validation failed for {logo_src}: {e}")
            raise PatcherError(
                "The specified logo is not a valid image file. Please try again.",
                path=logo_src,
                error_msg=str(e),
            )

        logo_dest = self.ui_config.plist_manager.plist_path.parent / "logo.png"
        self.ui_config._copy_file(logo_src, logo_dest)
        return str(logo_dest)

    def validate_creds(
        self, creds: dict, required_keys: tuple[str, ...], setup_type: SetupType
    ) -> None:
        """
        Validates all required keys are present in the credentials.

        :param creds: Credentials to validate
        :type creds: dict
        :param required_keys: Keys required to be present in passed credentials.
        :type required_keys: tuple[str, ...]
        :param setup_type: The ``SetupType`` to validate credentials against.
        :type setup_type: SetupType
        :raises SetupError: If any credentials are missing.
        """
        self.log.info(f"Validating credentials for {setup_type.value} setup.")
        missing_keys = [key for key in required_keys if not creds.get(key)]
        if missing_keys:
            self.log.error(
                f"Missing required credential(s): {', '.join(missing_keys)} for {setup_type.value} setup."
            )
            raise SetupError(
                "Missing required credentials.",
                credential=", ".join(missing_keys),
                setup_type=setup_type.value,
            )

    def prompt_installomator(self) -> None:
        """
        Prompts user to enable or disable InstallomatorClient support.

        If enabled, assists in identifying :class:`~patcher.core.models.patch.PatchTitle` objects with InstallomatorClient support,
        used during :ref:`analyze <analyze>` commands.
        """
        use_installomator = click.confirm(
            "Would you like to enable InstallomatorClient support?", default=True
        )
        self.plist_manager.set("enable_installomator", use_installomator)

    async def get_token(
        self, setup_type: SetupType = SetupType.STANDARD, creds: dict | None = None
    ) -> str | AccessToken:
        """
        Fetches a Token (basic or ``AccessToken``) depending on setup type (Standard or SSO).

        :param setup_type: ``SetupType`` specified dictates which type of Token will be retrieved (basic or bearer).
        :type setup_type: SetupType
        :param creds: If ``SetupType`` is "Standard", the user credentials needed to obtain a basic token.
        :type creds: dict | None
        :raises SetupError: If either type of Token could not be obtained.
        :return: For ``SetupType.STANDARD``, the basic token is returned. For ``SetupType.SSO``, the ``AccessToken`` object is returned.
        :rtype: str | AccessToken
        """
        if setup_type == SetupType.SSO:
            token_manager = TokenManager(self.config)
            try:
                token = await token_manager.fetch_token()
                token_manager.save_token(token)
                return token
            except TokenError as e:
                raise SetupError(
                    "Failed to obtain an AccessToken during setup. Please check your credentials and try again.",
                    error_msg=str(e),
                )
        elif setup_type == SetupType.STANDARD:
            api_client = HTTPClient()
            try:
                return await api_client.fetch_basic_token(
                    username=creds.get("USERNAME"),
                    password=creds.get("PASSWORD"),
                    jamf_url=creds.get("URL"),
                )
            except (KeyError, APIResponseError) as e:
                self.log.error(
                    f"Unable to retrieve basic token with provided username {creds.get('USERNAME')} and password. Details: {e}"
                )
                raise SetupError(
                    "Failed to obtain a Basic Token during setup. Please check your credentials and try again.",
                    error_msg=str(e),
                )

    async def create_api_client(self, basic_token: str, jamf_url: str) -> tuple[str, str]:
        """
        Creates API Role and Client for standard setup types.

        :param basic_token: The basic token used for authorization in creating API Role and Client
        :type basic_token: str
        :param jamf_url: The Jamf Pro instance URL to create API Role and Clients in.
        :type jamf_url: str
        :raises SetupError: If either the API Role or API Client could not be created.
        :return: The client ID and client secret of the created API Client and Role.
        :rtype: tuple[str, str]
        """
        api_client = HTTPClient()
        if not await api_client.create_roles(token=basic_token, jamf_url=jamf_url):
            self.log.error(
                "Failed to create API role as expected during setup. Verify SSO is not being used in Jamf instance."
            )
            raise SetupError("Failed to create API Role during Setup. Check logs for more details.")
        else:
            try:
                client_id, client_secret = await api_client.create_client(
                    token=basic_token, jamf_url=jamf_url
                )
                return client_id, client_secret
            except APIResponseError as e:
                self.log.error(f"Unable to create API client as expected. Details: {e}")
                raise SetupError(
                    "Failed to create Patcher API Client as expected.", error_msg=str(e)
                )

    async def bootstrap_noninteractive(
        self,
        client_id: str,
        client_secret: str,
        url: str,
    ) -> None:
        """
        Non-interactive setup path for CI/CD environments.

        Skips all prompts (setup type, InstallomatorClient, UI configuration). The provided
        credentials are stored via the configured :class:`ConfigManager`. When that
        manager is in in-memory mode (the typical CI/CD setup) the macOS keychain is
        not touched. An access token is then fetched so subsequent API calls succeed.

        Setup completion is marked in memory only, with no plist mutation. The next
        invocation will need to provide credentials again, which is the desired
        behavior on ephemeral runners.

        :param client_id: Jamf Pro API client ID.
        :type client_id: str
        :param client_secret: Jamf Pro API client secret.
        :type client_secret: str
        :param url: Jamf Pro instance URL.
        :type url: str
        :raises SetupError: If a token cannot be obtained with the provided credentials.
        """
        self.log.info("Bootstrapping Patcher in non-interactive mode.")

        self.config.set_credential("URL", url)
        self.config.set_credential("CLIENT_ID", client_id)
        self.config.set_credential("CLIENT_SECRET", client_secret)

        token_manager = TokenManager(self.config)
        try:
            await token_manager.fetch_token()
        except TokenError as e:
            self.log.error(f"Non-interactive token fetch failed. Details: {e}")
            raise SetupError(
                "Failed to obtain an AccessToken in non-interactive mode. "
                "Verify the provided credentials are correct.",
                error_msg=str(e),
            )

        # Mark completion in memory only; do not write to plist.
        self._completed = True
        self.log.info("Non-interactive bootstrap completed successfully.")

    async def start(self, animator: Animation | None = None, fresh: bool = False) -> None:
        """
        Run the interactive setup flow end-to-end.

        Returns early if setup has already completed unless ``fresh=True`` is
        passed (which re-runs the full flow regardless of previous completion).
        Prompts for setup type, then walks the full path: credentials → API
        role + client creation (Standard only) → bearer token fetch →
        ``JamfClient`` save → UI configuration → mark complete.

        **Options**:

        - :attr:`~patcher.cli.setup.SetupType.STANDARD` prompts for admin
          username/password, fetches a basic token, creates the API role +
          client on the Jamf side, and saves the resulting client credentials.
        - :attr:`~patcher.cli.setup.SetupType.SSO` prompts for an existing
          API client ID + secret and saves them directly.

        .. seealso::
            For SSO users, reference our :ref:`handling-sso` page for
            assistance creating an API integration.

        .. note::
            If a previous attempt failed after the Jamf API role + client
            were created, a Standard re-run will fail with a ``400`` because
            those objects already exist. Either delete them from Jamf and
            retry, or switch to SSO setup and reuse them.

        :param animator: The animation instance to update messages. Defaults
            to ``self.animator``.
        :type animator: Animation | None
        :param fresh: If True, re-run setup even when already completed.
        :type fresh: bool
        :raises SetupError: If a token cannot be fetched, credentials are
            missing, or any other setup step fails.
        """
        if self.completed and not fresh:
            return

        animator = animator or self.animator
        self._greet()

        setup_type_map = {1: SetupType.STANDARD, 2: SetupType.SSO}
        # Loop until a valid setup type is chosen. Previously this branch
        # recursively called ``self.start()`` on invalid input, which blew the
        # Python stack with ~1000 frames if the prompt produced a non-int
        # (e.g. asyncclick's async-aware ``prompt`` returning a coroutine
        # because the caller didn't ``await`` it). See issue #58.
        while True:
            choice = await click.prompt(
                "Choose setup method (1: Standard setup, 2: SSO setup)",
                type=int,
                default=1,
            )
            if choice in setup_type_map:
                break
            click.echo(click.style("Invalid choice, please choose 1 or 2", fg="red"))
        setup_type = setup_type_map[choice]

        creds = await self.prompt_credentials(setup_type)
        self.prompt_installomator()

        if setup_type == SetupType.STANDARD:
            self.validate_creds(creds, ("USERNAME", "PASSWORD", "URL"), SetupType.STANDARD)
            await animator.update_msg("Retrieving basic token")
            basic_token = await self.get_token(setup_type=setup_type, creds=creds)
            await animator.update_msg("Creating API integrations")
            client_id, client_secret = await self.create_api_client(basic_token, creds.get("URL"))
            self._save_creds(
                {"URL": creds.get("URL"), "CLIENT_ID": client_id, "CLIENT_SECRET": client_secret}
            )
        else:  # SSO
            self.validate_creds(creds, ("CLIENT_ID", "CLIENT_SECRET", "URL"), SetupType.SSO)
            await animator.update_msg("Saving credentials...")
            self._save_creds(creds)

        await animator.update_msg("Fetching AccessToken")
        client_creds = self._get_creds()
        await self.get_token(setup_type=SetupType.SSO, creds=client_creds)

        await animator.update_msg("Creating JamfClient...")
        client_creds = self._get_creds(include_token=True)
        token = AccessToken(
            token=client_creds.get("TOKEN"), expires=client_creds.get("TOKEN_EXPIRATION")
        )
        self.config.create_client(
            JamfClient(
                client_id=client_creds.get("CLIENT_ID"),
                client_secret=client_creds.get("CLIENT_SECRET"),
                server=client_creds.get("URL"),
            ),
            token=token,
        )

        await animator.stop()
        await self.prompt_ui_settings()
        self._mark_completion(value=True)

    def reset_setup(self) -> bool:
        """
        Resets setup completion flag, removing the ``setup_completed`` key/value from the property list.

        This effectively marks Setup completion as False and will re-trigger the setup assistant.

        .. admonition:: Warning!
            :class: danger

            The Jamf API will return a ``400`` response if API Roles/Clients exist already in the Jamf instance specified.
            It is important to remove the API Role and Client objects before re-running the Setup assistant.

        :return: ``True`` if the Setup section in the property list file was removed.
        :rtype: bool
        """
        self.log.debug("Attempting to reset setup.")
        success = self.plist_manager.remove("setup_completed")
        if success:
            self._completed = None
            self.log.info("Successfully reset setup.")
        return success
