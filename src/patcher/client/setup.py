from enum import Enum
from typing import Dict, Optional, Tuple, Union

import asyncclick as click

from ..models.jamf_client import JamfClient
from ..models.token import AccessToken
from ..utils.animation import Animation
from ..utils.exceptions import APIResponseError, SetupError, TokenError
from ..utils.logger import LogMe
from . import BaseAPIClient
from .config_manager import ConfigManager
from .plist_manager import PropertyListManager
from .token_manager import TokenManager
from .ui_manager import UIConfigManager

# Welcome messages
GREET = "Thanks for downloading Patcher!\n"
WELCOME = """It looks like this is your first time using the tool. We will guide you through the initial setup to get you started.

The setup assistant will prompt you to choose your setup method--Standard is the automated setup which will prompt for your Jamf URL, your Jamf Pro username and your Jamf Pro password. Patcher ONLY uses this information to create the necessary API role and client on your behalf, your credentials are not stored whatsoever. Once generated, these client credentials (and generated bearer token) can be found in your keychain. The SSO setup will prompt for a client ID and client secret of an API Client that has already been created. 

You will be prompted to enter in the header and footer text for PDF reports, along with optional custom fonts and branding logo. These can be configured later by modifying the corresponding keys in the com.liquidzoo.patcher.plist file in Patcher's Application Support directory stored in the user library.

"""
DOC = "For more information, visit the project documentation: https://patcher.liquidzoo.io\n"


class SetupType(Enum):
    STANDARD = "standard"
    SSO = "sso"


class Setup:
    def __init__(
        self,
        config: ConfigManager,
        ui_config: UIConfigManager,
        plist_manager: PropertyListManager,
    ):
        """
        Handles the initial setup process for the Patcher CLI tool.

        This class guides users through configuring the necessary components to integrate
        with their Jamf environment. The setup includes creating API roles, clients, and configuring
        user interface settings for PDF reports.

        :param config: Manages application configuration, including credential storage.
        :type config: :class:`~patcher.client.config_manager.ConfigManager`
        :param ui_config: Handles UI-related configurations for the setup process.
        :type ui_config: :class:`~patcher.client.ui_manager.UIConfigManager`
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
        :rtype: :py:class:`bool`
        """
        if self._completed is None:
            self.log.debug("Checking setup completion status.")
            self._completed = self.plist_manager.get("setup_completed") or False
        return self._completed

    @staticmethod
    def _greet():
        """Displays the greeting and welcome messages."""
        click.echo(click.style(GREET, fg="cyan", bold=True))
        click.echo(click.style(WELCOME), nl=False)
        click.echo(click.style(DOC, fg="bright_magenta", bold=True))

    def _mark_completion(self, value: bool = False):
        """Updates the plist file to reflect the completion status of the setup."""
        self.plist_manager.set("setup_completed", value)
        self._completed = value

    def _prompt_credentials(self, setup_type: SetupType) -> Optional[Dict]:
        """Prompt for credentials based on the credential type."""
        self.log.info(f"Prompting user for {setup_type.value} credentials.")
        if setup_type == SetupType.STANDARD:
            return {
                "URL": click.prompt("Enter your Jamf Pro URL"),
                "USERNAME": click.prompt("Enter your Jamf Pro username"),
                "PASSWORD": click.prompt("Enter your Jamf Pro password", hide_input=True),
            }
        elif setup_type == SetupType.SSO:
            return {
                "URL": click.prompt("Enter your Jamf Pro URL"),
                "CLIENT_ID": click.prompt("Enter your API Client ID"),
                "CLIENT_SECRET": click.prompt("Enter your API Client Secret"),
            }

    def _validate_creds(
        self, creds: Dict, required_keys: Tuple[str, ...], setup_type: SetupType
    ) -> None:
        """Validates all required keys are present in the credentials."""
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

    def _save_creds(self, creds: Dict) -> None:
        """Save gathered credentials to keychain."""
        for key, value in creds.items():
            self.config.set_credential(key, value)

    def _prompt_installomator(self):
        """Prompts user to enable or disable Installomator support."""
        use_installomator = click.confirm(
            "Would you like to enable Installomator support?", default=True
        )
        self.plist_manager.set("enable_installomator", use_installomator)

    async def _token_fetching(
        self, setup_type: SetupType = SetupType.STANDARD, creds: Optional[Dict] = None
    ) -> Optional[Union[str, AccessToken]]:
        """Fetches a Token (basic or ``AccessToken``) depending on setup type (Standard or SSO)."""
        if setup_type == SetupType.SSO:
            token_manager = TokenManager(self.config)
            try:
                return await token_manager.fetch_token()
            except TokenError as e:
                raise SetupError(
                    "Failed to obtain an AccessToken during setup. Please check your credentials and try again.",
                    error_msg=str(e),
                )
        elif setup_type == SetupType.STANDARD:
            api_client = BaseAPIClient()
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

    async def _configure_integration(
        self, basic_token: str, jamf_url: str
    ) -> Optional[Tuple[str, str]]:
        """Creates API Role and Client for standard setup types."""
        api_client = BaseAPIClient()
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

    async def _run_setup(self, setup_type: SetupType, animator: Optional[Animation] = None) -> None:
        """Handles both types of setup for end-users based on passed `setup_type`."""
        if self.completed:
            return

        # Setup animation
        animator = animator or self.animator

        # Prompt for credentials
        creds = self._prompt_credentials(setup_type)

        # Prompt for installomator
        self._prompt_installomator()

        if setup_type == SetupType.STANDARD:
            # `launch` method
            self.log.debug(
                "Detected first run has not been completed. Starting standard (non-SSO) Setup..."
            )

            # Validate needed credentials are present
            await animator.update_msg("Starting Standard setup...")
            self._validate_creds(creds, ("USERNAME", "PASSWORD", "URL"), setup_type)

            # Extract jamf_url
            jamf_url = creds.get("URL")

            # Retrieve basic token
            await animator.update_msg("Retrieving basic token")
            basic_token = await self._token_fetching(setup_type=SetupType.STANDARD, creds=creds)

            # Create API Role and Client
            await animator.update_msg("Creating API integrations")
            client_id, client_secret = await self._configure_integration(
                basic_token=basic_token, jamf_url=jamf_url
            )

            # Save credentials
            client_creds = {"URL": jamf_url, "CLIENT_ID": client_id, "CLIENT_SECRET": client_secret}
            self._save_creds(client_creds)

            # Retrieve AccessToken
            await animator.update_msg("Fetching AccessToken")
            token = await self._token_fetching(setup_type=SetupType.SSO, creds=client_creds)

            # Setup JamfClient
            await animator.update_msg("Creating JamfClient...")
            self.config.create_client(
                JamfClient(
                    client_id=client_id,
                    client_secret=client_secret,
                    server=jamf_url,
                ),
                token=token,
            )
        elif setup_type == SetupType.SSO:
            # `first_run` method
            self.log.debug("Detected first run has not been completed. Starting SSO setup...")

            # Ensure client ID and client secret are present in credentials
            await animator.update_msg("Starting SSO setup...")
            self._validate_creds(creds, ("CLIENT_ID", "CLIENT_SECRET", "URL"), setup_type)

            # Store credentials
            await animator.update_msg("Saving credentials...")
            self._save_creds(creds)

            # Fetch token
            await animator.update_msg("Fetching AccessToken...")
            token = await self._token_fetching(setup_type=SetupType.SSO, creds=creds)

            # Setup JamfClient
            await animator.update_msg("Creating JamfClient...")
            self.config.create_client(
                JamfClient(
                    client_id=creds.get("CLIENT_ID"),
                    client_secret=creds.get("CLIENT_SECRET"),
                    server=creds.get("URL"),
                ),
                token=token,
            )

        # Set stop event before prompting
        await animator.stop()

        # Setup UI components
        self.ui_config.setup_ui()

        # Mark setup as complete
        self._mark_completion(value=True)

    async def start(self, animator: Optional[Animation] = None) -> None:
        """
        Allows the user to choose between different setup methods (Standard or SSO).

        An optional :class:`~patcher.utils.animation.Animation` object can be passed to update animation
        messages at runtime. Defaults to ``self.animator``.

        **Options**:

        - :attr:`~patcher.client.setup.SetupType.STANDARD` prompts for basic credentials, obtains basic token, creates API integration, saves client credentials and obtains an AccessToken.
        - :attr:`~patcher.client.setup.SetupType.SSO` prompts for existing API credentials, obtains AccessToken and saves credentials.

        .. seealso::
            For SSO users, reference our :ref:`handling-sso` page for assistance creating an API integration.

        :param animator: The animation instance to update messages. Defaults to ``self.animator``.
        :type animator: :py:obj:`~typing.Optional` [:class:`~patcher.utils.animation.Animation`]
        :raises SetupError: If a token could not be fetched, credentials are missing or setup could not be marked complete.
        """
        if self.completed:
            return

        # Greet users
        self._greet()

        animator = animator or self.animator

        setup_type_map = {1: SetupType.STANDARD, 2: SetupType.SSO}
        choice = click.prompt(
            "Choose setup method (1: Standard setup, 2: SSO setup)", type=int, default=1
        )
        if choice in setup_type_map:
            await self._run_setup(setup_type_map[choice], animator=animator)
        else:
            click.echo(click.style("Invalid choice, please choose 1 or 2", fg="red"))
            await self.start()

    def reset_setup(self) -> bool:
        """
        Resets setup completion flag (), removing the ``setup_completed`` key/value from the property list.

        This effectively marks Setup completion as False and will re-trigger the setup assistant.

        :return: ``True`` if the Setup section in the property list file was removed.
        :rtype: :py:class:`bool`
        """
        self.log.debug("Attempting to reset setup.")
        success = self.plist_manager.remove("setup_completed")
        if success:
            self._completed = None
            self.log.info("Successfully reset setup.")
        return success
