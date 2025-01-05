import os
import plistlib
from asyncio import sleep
from typing import Optional

import asyncclick as click

from ..models.jamf_client import JamfClient
from ..utils import exceptions, logger
from ..utils.animation import Animation
from . import BaseAPIClient
from .config_manager import ConfigManager
from .token_manager import TokenManager
from .ui_manager import UIConfigManager

# Welcome messages
GREET = "Thanks for downloading Patcher!\n"
WELCOME = """It looks like this is your first time using the tool. We will guide you through the initial setup to get you started.

The setup assistant will prompt you to choose your setup method--Standard is the automated setup which will prompt for your Jamf URL, your Jamf Pro username and your Jamf Pro password. Patcher ONLY uses this information to create the necessary API role and client on your behalf, your credentials are not stored whatsoever. Once generated, these client credentials (and generated bearer token) can be found in your keychain. The SSO setup will prompt for a client ID and client secret of an API Client that has already been created. 

You will be prompted to enter in the header and footer text for PDF reports, should you choose to generate them. These can be configured later by modifying the corresponding keys in the com.liquidzoo.patcher.plist file in Patcher's Application Support directory stored in the user library.

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
        :type config: ConfigManager
        :param ui_config: Handles UI-related configurations for the setup process.
        :type ui_config: UIConfigManager
        """
        self.config = config
        self.ui_config = ui_config
        self.log = logger.LogMe(self.__class__.__name__)
        self.plist_path = ui_config.plist_path
        self._completed = None
        self.animator = Animation()

    @property
    def completed(self) -> bool:
        """
        Indicates whether the setup process has been completed.

        :return: True if setup has been completed, False otherwise.
        :rtype: bool
        """
        return self._completed if self._completed is not None else self._check_completion()

    def _check_completion(self):
        """
        Determines if the setup has been completed by checking the presence of a plist file.

        :return: True if setup has been completed, False otherwise.
        :rtype: bool
        :raises exceptions.PlistError: If there is an error reading the plist file.
        """
        self.log.debug("Checking for presence of .plist file")
        if self.plist_path.exists():
            try:
                with open(self.plist_path, "rb") as fp:
                    plist_data = plistlib.load(fp)
                    self._completed = plist_data.get("Setup", {}).get("first_run_done", False)
            except Exception as e:
                self.log.error(f"Error reading plist file: {e}")
                raise exceptions.PlistError(path=str(self.plist_path))
        else:
            self._completed = False
        return self._completed

    def _set_plist(self, value: bool = False):
        """
        Updates the plist file to reflect the completion status of the setup.

        :param value: Indicates whether the setup is complete. Default is False.
        :type value: bool
        :raises exceptions.PlistError: If there is an error writing to the plist file.
        """
        try:
            if os.path.exists(self.plist_path):
                with open(self.plist_path, "rb") as fp:
                    plist_data = plistlib.load(fp)
            else:
                plist_data = {}

            plist_data.setdefault("Setup", {})["first_run_done"] = value
            os.makedirs(os.path.dirname(self.plist_path), exist_ok=True)
            with open(self.plist_path, "wb") as fp:
                plistlib.dump(plist_data, fp)
        except Exception as e:
            self.log.error(f"Error writing to plist file: {e}")
            raise exceptions.PlistError(path=str(self.plist_path))

    @staticmethod
    def _greet():
        """
        Displays the greeting and welcome messages.
        """
        click.echo(click.style(GREET, fg="cyan", bold=True))
        click.echo(click.style(WELCOME), nl=False)
        click.echo(click.style(DOC, fg="bright_magenta", bold=True))

    async def prompt_method(self, animator: Optional[Animation] = None):
        """
        Allows the user to choose between different setup methods (Standard or SSO).

        This method enhances the user experience by guiding them through the appropriate setup steps based on their environment.

        :param animator: Animation object to pass to methods for progress updates. Defaults to `self.animator`.
        :type animator: Optional[Animation]
        """
        if self.completed:
            return
        self._greet()
        anim = animator or self.animator

        try:
            choice = click.prompt(
                "Choose setup method (1: Standard setup, 2: SSO setup)", type=int, default=1
            )
            if choice == 1:
                await self.launch(animator=anim)
            elif choice == 2:
                await self.first_run()
            else:
                click.echo(click.style("Invalid choice, please choose 1 or 2.", fg="red"))
                await self.prompt_method()
        except ValueError as e:
            self.log.error(f"Invalid input during setup method selection: {e}")
            click.echo(click.style("Invalid input. Please enter 1 or 2.", fg="red"))
            await self.prompt_method()

    async def first_run(self):
        """
        Initiates the setup process for users utilizing SSO.

        This method handles the necessary steps for generating and saving API client credentials
        when the user is operating in an SSO environment.

        :raises SystemExit: If the user opts not to proceed with the setup.
        :raises exceptions.TokenFetchError: If there is an error fetching the token.
        """
        if not self.completed:
            self.log.info("Detected first run has not been completed. Starting setup assistant...")
            api_url = click.prompt("Enter your Jamf Pro URL")
            api_client_id = click.prompt("Enter your API Client ID")
            api_client_secret = click.prompt("Enter your API Client Secret")

            # Store credentials
            self.config.set_credential("URL", api_url)
            self.config.set_credential("CLIENT_ID", api_client_id)
            self.config.set_credential("CLIENT_SECRET", api_client_secret)

            # Initialize TokenManager
            token_manager = TokenManager(self.config)
            token = await token_manager.fetch_token()

            # Wait a short time to ensure creds are saved
            await sleep(3)

            if token:
                jamf_client = JamfClient(
                    client_id=api_client_id,
                    client_secret=api_client_secret,
                    server=api_url,
                    token=token,
                )
                self.config.create_client(jamf_client)
                self.ui_config.setup_ui()
                self._set_plist(value=True)
                self._completed = True
            else:
                self.log.error("Failed to fetch a valid token!")
                raise exceptions.TokenFetchError(reason="Token failed verification")

    async def launch(self, animator: Optional[Animation] = None):
        """
        Launches the setup assistant for the Patcher tool.

        This method prompts the user for necessary information and handles the entire setup process,
        including API role creation, client creation, and saving credentials.

        :param animator: The animation instance to update messages. Defaults to `self.animator`.
        :type animator: Optional[Animation]
        :raises SystemExit: If the user opts not to proceed with the setup.
        :raises exceptions.TokenFetchError: If the API call to retrieve a token fails.
        :raises aiohttp.ClientError: If there is an error making the HTTP request.
        """
        animator = animator or self.animator
        if not self.completed:
            self.log.debug("Detected first run has not been completed. Starting setup assistant...")

            jamf_url = click.prompt("Enter your Jamf Pro URL")
            username = click.prompt("Enter your Jamf Pro username")
            password = click.prompt("Enter your Jamf Pro password", hide_input=True)

            # Initialize BaseAPIClient and TokenManager
            api_client = BaseAPIClient()
            token_manager = TokenManager(self.config)

            await animator.update_msg("Retrieving basic token")

            try:
                basic_token = await api_client.fetch_basic_token(
                    username=username, password=password, jamf_url=jamf_url
                )
                if not basic_token:
                    use_sso = click.confirm(
                        "Patcher was unable to retrieve a token. Are you using SSO?", default=False
                    )
                    if use_sso:
                        await self.first_run()
                        return
                    else:
                        basic_token = await api_client.fetch_basic_token(
                            username=username, password=password, jamf_url=jamf_url
                        )
                        if not basic_token:
                            click.echo(
                                click.style(
                                    text="Unfortunately Patcher was unable to retrieve a token again. Please verify your account does not use SSO.",
                                    fg="red",
                                ),
                                err=True,
                            )
            except exceptions.TokenFetchError:
                click.echo(
                    click.style(
                        text="Unfortunately we received an error trying to obtain a token. Please verify your account details and try again.",
                        fg="red",
                    ),
                    err=True,
                )
                return

            await animator.update_msg("Creating roles")
            role_created = await api_client.create_roles(token=basic_token, jamf_url=jamf_url)
            if not role_created:
                self.log.error("Failed creating API roles. Exiting...")
                click.echo(click.style("Failed to create API roles.", fg="red"), err=True)

            await animator.update_msg("Creating client")
            client_id, client_secret = await api_client.create_client(
                token=basic_token, jamf_url=jamf_url
            )

            await animator.update_msg("Saving URL and client credentials")
            # Create ConfigManager, save credentials
            self.config.set_credential("URL", jamf_url)
            self.config.set_credential("CLIENT_ID", client_id)
            self.config.set_credential("CLIENT_SECRET", client_secret)

            # Wait a short time to ensure creds are saved
            await sleep(3)

            await animator.update_msg("Fetching bearer token")
            # Fetch Token and save if successful
            token = await token_manager.fetch_token()
            if token:
                # Create JamfClient object with all credentials
                jamf_client = JamfClient(
                    client_id=client_id,
                    client_secret=client_secret,
                    server=jamf_url,
                    token=token,
                )
                self.config.create_client(jamf_client)
            else:
                self.log.error("Token failed validation. Notifying user and exiting...")
                click.echo(
                    click.style(
                        text="Token retrieved failed verification and we're unable to proceed!",
                        fg="red",
                    ),
                    err=True,
                )

            await animator.update_msg("Bearer token retrieved and JamfClient saved!")
            animator.stop_event.set()
            # Setup UI Configuration
            self.ui_config.setup_ui()

            # Set first run flag to True upon completion
            self._set_plist(value=True)
            self._completed = True

    async def reset(self):
        """
        Resets the UI configuration settings by clearing the existing configuration and starting the setup process again.

        This method is useful if the user wants to reconfigure the UI elements of PDF reports, such as header/footer text and font choices.
        """
        reset_config = self.ui_config.reset_config()
        if not reset_config:
            self.log.error("Encountered an issue resetting elements in config.ini.")
            raise OSError("The UI element configuration file could not be reset as expected.")
        else:
            self.ui_config.setup_ui()
