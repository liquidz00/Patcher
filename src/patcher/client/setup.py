import os
import plistlib
from asyncio import sleep
from typing import Dict, Optional

import asyncclick as click

from ..models.jamf_client import JamfClient
from ..utils.animation import Animation
from ..utils.exceptions import APIResponseError, SetupError
from ..utils.logger import LogMe
from . import BaseAPIClient
from .config_manager import ConfigManager
from .token_manager import TokenManager
from .ui_manager import UIConfigManager

# Welcome messages
GREET = "Thanks for downloading Patcher!\n"
WELCOME = """It looks like this is your first time using the tool. We will guide you through the initial setup to get you started.

The setup assistant will prompt you to choose your setup method--Standard is the automated setup which will prompt for your Jamf URL, your Jamf Pro username and your Jamf Pro password. Patcher ONLY uses this information to create the necessary API role and client on your behalf, your credentials are not stored whatsoever. Once generated, these client credentials (and generated bearer token) can be found in your keychain. The SSO setup will prompt for a client ID and client secret of an API Client that has already been created. 

You will be prompted to enter in the header and footer text for PDF reports, along with optional custom fonts and branding logo. These can be configured later by modifying the corresponding keys in the com.liquidzoo.patcher.plist file in Patcher's Application Support directory stored in the user library.

"""
DOC = "For more information, visit the project documentation: https://patcher.liquidzoo.io\n"


class Setup:
    """
    Handles the initial setup process for the Patcher CLI tool.

    This class guides users through configuring the necessary components to integrate
    with their Jamf environment. The setup includes creating API roles, clients, and configuring
    user interface settings for PDF reports.
    """

    def __init__(
        self,
        config: ConfigManager,
        ui_config: UIConfigManager,
    ):
        """
        Initializes the Setup class with configuration and UI configuration managers.

        :param config: Manages application configuration, including credential storage.
        :type config: :class:`~patcher.client.config_manager.ConfigManager`
        :param ui_config: Handles UI-related configurations for the setup process.
        :type ui_config: :class:`~patcher.client.ui_manager.UIConfigManager`
        """
        self.config = config
        self.ui_config = ui_config
        self.plist_path = ui_config.plist_path
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
            self._completed = self._check_completion()
        return self._completed

    def _check_completion(self) -> bool:
        """
        Determines if the setup has been completed by checking the presence of a plist file. If the
        property list file cannot be read, an error is logged.

        :return: True if setup has been completed, False otherwise.
        :rtype: bool
        """
        self.log.debug("Checking setup completion status.")
        if not os.path.exists(self.plist_path):
            self._completed = False

        try:
            with open(self.plist_path, "rb") as fp:
                plist_data = plistlib.load(fp)
                self._completed = plist_data.get("Setup", {}).get("first_run_done", False)
        except plistlib.InvalidFileException as e:
            self.log.error(f"Unable to read property list file. Details: {e}")
            self._completed = False

        return self._completed

    def _mark_completion(self, value: bool = False):
        """
        Updates the plist file to reflect the completion status of the setup.

        :param value: Indicates whether the setup is complete. Default is False.
        :type value: bool
        """
        plist_data = {"Setup": {"first_run_done": value}}
        os.makedirs(os.path.dirname(self.plist_path), exist_ok=True)
        try:
            with open(self.plist_path, "wb") as fp:
                plistlib.dump(plist_data, fp)
        except plistlib.InvalidFileException as e:
            self.log.error(f"Could not write to property list ({self.plist_path}). Details: {e}")
            raise SetupError(
                "Error encountered trying to write to property list file", path=str(self.plist_path)
            ) from e

    @staticmethod
    def _greet():
        """
        Displays the greeting and welcome messages.
        """
        click.echo(click.style(GREET, fg="cyan", bold=True))
        click.echo(click.style(WELCOME), nl=False)
        click.echo(click.style(DOC, fg="bright_magenta", bold=True))

    def _prompt_credentials(self, setup_type: str) -> Dict:
        """
        Prompt for credentials based on the credential type.

        :param setup_type: The type of credentials to prompt for. Options are 'basic' or 'sso'.
        :type setup_type: str
        :return: A dictionary containing the prompted credentials.
        :rtype: Dict
        """
        self.log.info(f"Prompting user for {setup_type} credentials.")
        if setup_type == "basic":
            return {
                "URL": click.prompt("Enter your Jamf Pro URL"),
                "USERNAME": click.prompt("Enter your Jamf Pro username"),
                "PASSWORD": click.prompt("Enter your Jamf Pro password", hide_input=True),
            }
        elif setup_type == "sso":
            return {
                "URL": click.prompt("Enter your Jamf Pro URL"),
                "CLIENT_ID": click.prompt("Enter your API Client ID"),
                "CLIENT_SECRET": click.prompt("Enter your API Client Secret"),
            }

    def _save_creds(self, creds: Dict) -> None:
        """
        Save gathered credentials to keychain.

        :param creds: Credentials to save.
        :type creds: Dict
        """
        for key, value in creds.items():
            self.config.set_credential(key, value)

    async def prompt_method(self):
        """
        Allows the user to choose between different setup methods (Standard or SSO), guiding
        them through the appropriate setup steps based on their environment.
        """
        if self.completed:
            return

        self._greet()

        choice = click.prompt(
            "Choose setup method (1: Standard setup, 2: SSO setup)", type=int, default=1
        )
        if choice == 1:
            await self.launch()
        elif choice == 2:
            await self.first_run()
        else:
            click.echo(click.style("Invalid choice, please choose 1 or 2.", fg="red"))
            await self.prompt_method()

    async def first_run(self, animator: Optional[Animation] = None):
        """
        Initiates the setup process for users utilizing SSO, prompting users for existing API credentials.

        .. seealso::

            For assistance creating an API integration with Jamf Pro, visit our
            :doc:`Prerequisites <user/prereqs#handling-sso>` page.

        :param animator: The animation instance to update messages. Defaults to `self.animator`.
        :type animator: :class:`~patcher.utils.animation.Animation`
        """
        animator = animator or self.animator

        if self.completed:
            return

        self.log.debug("Detected first run has not been completed. Starting SSO setup...")

        # Prompt for creds
        await animator.update_msg("Prompting for credentials...")
        creds = self._prompt_credentials("sso")
        jamf_url, client_id, client_secret = (
            creds.get("URL"),
            creds.get("CLIENT_ID"),
            creds.get("CLIENT_SECRET"),
        )

        # Store credentials
        await animator.update_msg("Saving credentials...")
        self._save_creds(creds)

        # Initialize TokenManager
        await animator.update_msg("Fetching AccessToken...")
        token_manager = TokenManager(self.config)
        token = await token_manager.fetch_token()

        # Wait a short time to ensure creds are saved
        await sleep(2)

        await animator.update_msg("Creating JamfClient...")
        self.config.create_client(
            JamfClient(
                client_id=client_id,
                client_secret=client_secret,
                server=jamf_url,
                token=token,
            )
        )

        # Stop animator before prompting
        await animator.stop_event.set()
        self.ui_config.setup_ui()

        # Set completion
        self._mark_completion(value=True)

    async def launch(self, animator: Optional[Animation] = None):
        """
        Initiates the setup process for users not utilizing SSO.

        This method prompts the user for necessary information and handles the entire setup process,
        including API role creation, client creation, and saving credentials.

        :param animator: The animation instance to update messages. Defaults to `self.animator`.
        :type animator: Optional[:class:`~patcher.utils.animation.Animation`]
        :raises SystemExit: If the user opts not to proceed with the setup.
        :raises SetupError: If the API call to retrieve a token fails.
        """
        animator = animator or self.animator

        if self.completed:
            return

        self.log.debug(
            "Detected first run has not been completed. Starting automatic (non-SSO) Setup..."
        )

        # Prompt for creds
        creds = self._prompt_credentials("basic")
        jamf_url, username, password = (
            creds.get("URL"),
            creds.get("USERNAME"),
            creds.get("PASSWORD"),
        )

        # Initialize BaseAPIClient
        api_client = BaseAPIClient()

        await animator.update_msg("Retrieving basic token")

        try:
            basic_token = await api_client.fetch_basic_token(
                username=username, password=password, jamf_url=jamf_url
            )
        except APIResponseError as e:
            self.log.error(
                f"Error received obtaining a token during setup (1st attempt). Details: {e}"
            )
            raise SetupError(
                "Unfortunately we received an error trying to obtain a token. Please verify your account details and try again."
            ) from e

        if not basic_token:
            choice = click.prompt(
                "Patcher wasn't able to retrieve a basic token. How would you like to proceed? (1: Retry, 2: Use SSO setup, 3: Exit)",
                type=int,
                default=1,
            )
            if choice == 1:
                try:
                    basic_token = await api_client.fetch_basic_token(
                        username=username, password=password, jamf_url=jamf_url
                    )
                except APIResponseError as e:
                    self.log.error(
                        f"Failed to retrieve a basic token after second attempt. Suspect SSO may be in use. Details: {e}"
                    )
                    raise SetupError(
                        "Unfortunately Patcher was unable to retrieve a token again. Please verify your account does not use SSO."
                    ) from e
            elif choice == 2:
                await self.first_run()
                return
            elif choice == 3:
                # User chose to quit
                self.log.info("User chose to quit Setup as basic token could not be retrieved.")
                return

        await animator.update_msg("Creating API role")
        role_created = await api_client.create_roles(token=basic_token, jamf_url=jamf_url)
        if not role_created:
            self.log.error("Failed to create API role as expected.")
            raise SetupError(
                "Failed to create API roles. Check logs for more details.", url=jamf_url
            )

        await animator.update_msg("Creating API client")
        try:
            client_id, client_secret = await api_client.create_client(
                token=basic_token, jamf_url=jamf_url
            )
        except APIResponseError as e:
            self.log.error(f"Unable to create API client as expected. Details: {e}")
            raise SetupError from e

        await animator.update_msg("Saving URL and client credentials")

        # Create ConfigManager, save credentials
        creds = {"URL": jamf_url, "CLIENT_ID": client_id, "CLIENT_SECRET": client_secret}
        self._save_creds(creds)

        # Wait a short time to ensure creds are saved
        await sleep(2)

        # Initialize token manager
        token_manager = TokenManager(self.config)

        # Fetch Token and save if successful
        await animator.update_msg("Fetching bearer token")
        token = await token_manager.fetch_token()

        # Create JamfClient object with all credentials
        await animator.update_msg("Creating JamfClient object...")
        self.config.create_client(
            JamfClient(
                client_id=client_id,
                client_secret=client_secret,
                server=jamf_url,
                token=token,
            )
        )
        # Stop animation for UI prompts
        await animator.stop_event.set()

        # Setup UI Configuration
        self.ui_config.setup_ui()

        # Set first run flag to True upon completion
        self._mark_completion(value=True)

    async def reset(self):
        """
        Resets the UI configuration settings by clearing the existing configuration and starting the setup process again.

        This method is useful if the user wants to reconfigure the UI elements of PDF reports, such as header/footer text, font choices, and branding logo.
        """
        reset_config = self.ui_config.reset_config()
        if not reset_config:
            self.log.error("Encountered an issue resetting elements in config.ini.")
            raise OSError("The UI element configuration file could not be reset as expected.")
        else:
            self.ui_config.setup_ui()
