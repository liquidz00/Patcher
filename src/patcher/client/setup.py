import os
import plistlib
import shutil
import sys
from asyncio import Lock, sleep
from configparser import ConfigParser
from typing import AnyStr, Optional, Tuple

import aiohttp
import click

from ..models.token import AccessToken
from ..utils import exceptions, logger
from .config_manager import ConfigManager
from .token_manager import TokenManager
from .ui_manager import UIConfigManager

logthis = logger.setup_child_logger("Setup", __name__)

# Welcome messages
GREET = "Thanks for downloading patcher!\n"

WELCOME = """It looks like this is your first time using the tool. We will guide you through the initial setup to get you started.

The setup assistant will prompt you for your Jamf URL, your Jamf Pro username and your Jamf Pro password. Patcher ONLY uses this information to create the necessary API roles and Clients on your behalf, your credentials are not stored whatsoever. A Client ID, Client Secret, and Bearer Token will be generated for you and saved to your keychain.
Once the token has been retrieved and saved, you will be prompted to enter in the header and footer text for PDF reports, should you choose to generate them.

For more information, visit our project wiki: https://github.com/liquidz00/Patcher/wiki

"""
CONTRIBUTE = "Want to contribute? We'd welcome it! Submit a feature request on the repository and we will reach out as soon as possible!\n"


class Setup:
    """
    A class to handle the setup process for the Patcher tool.
    """

    def __init__(
        self,
        config: ConfigManager,
        token_manager: TokenManager,
        ui_config: UIConfigManager,
    ):
        """
        Initializes the Setup class with the provided configuration, token manager, and UI configuration.

        :param config: The configuration manager instance.
        :type config: ConfigManager
        :param token_manager: The token manager instance.
        :type token_manager: TokenManager
        :param ui_config: The UI configuration manager instance.
        :type ui_config: UIConfigManager
        """
        self.config = config
        self.token_manager = token_manager
        self.ui_config = ui_config
        self.plist_path = os.path.expanduser(
            "~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist"
        )
        self._completed = False
        self.token = None
        self.jamf_url = None
        self.lock = Lock()
        self.log = logthis

    @property
    def completed(self) -> bool:
        """
        Checks if the setup process has been completed.

        :return: True if setup completed, False otherwise.
        :rtype: bool
        """
        return self._completed

    @completed.setter
    def completed(self, value: bool):
        """
        Sets the setup process completion status.

        :param value: True if setup completed, False otherwise.
        :type value: bool
        """
        self._completed = value

    def _is_complete(self):
        """
        Checks for the presence of the plist file to determine if setup has been completed.

        :raises exceptions.PlistError: If there is an error reading the plist file.
        """
        self.log.debug("Checking for presence of .plist file")
        if os.path.exists(self.plist_path):
            try:
                with open(self.plist_path, "rb") as fp:
                    plist_data = plistlib.load(fp)
                    self.completed = plist_data.get("first_run_done", False)
            except Exception as e:
                self.log.error(f"Error reading plist file: {e}")
                raise exceptions.PlistError

    @staticmethod
    def _greet():
        """
        Displays the greeting and welcome messages.
        """
        click.echo(click.style(GREET, fg="cyan", bold=True))
        click.echo(click.style(WELCOME, fg="white"), nl=False)
        click.echo(click.style(CONTRIBUTE, fg="yellow"))

    def _set_complete(self):
        """
        Sets the setup completion flag to True by updating the plist file.

        :raises exceptions.PlistError: If there is an error writing to the plist file.
        """
        plist_data = {"first_run_done": True}
        try:
            os.makedirs(os.path.dirname(self.plist_path), exist_ok=True)
            with open(self.plist_path, "wb") as fp:
                plistlib.dump(plist_data, fp)
            self.completed = True
        except Exception as e:
            self.log.error(f"Error writing to plist file: {e}")
            raise exceptions.PlistError(path=self.plist_path)

    def _setup_ui(self):
        """
        Prompts the user to enter UI configuration settings and saves them to the configuration file.

        :raises FileNotFoundError: IF the specified font file paths do not exist.
        """
        header_text = click.prompt("Enter the Header Text to use on PDF reports")
        footer_text = click.prompt("Enter the Header Text to use on PDF reports")

        use_custom_font = click.confirm("Would you like to use a custom font?", default=False)
        font_dir = os.path.join(self.ui_config.user_config_dir, "fonts")
        os.makedirs(font_dir, exist_ok=True)

        if use_custom_font:
            font_name = click.prompt("Enter the custom font name", default="CustomFont")
            font_regular_src_path = click.prompt("Enter the path to the regular font file")
            font_bold_src_path = click.prompt("Enter the path to the bold font file")
            font_regular_dest_path = os.path.join(font_dir, os.path.basename(font_regular_src_path))
            font_bold_dest_path = os.path.join(font_dir, os.path.basename(font_bold_src_path))

            # Copy files
            shutil.copy(font_regular_src_path, font_regular_dest_path)
            shutil.copy(font_bold_src_path, font_bold_dest_path)
        else:
            font_name = "Assistant"
            font_regular_dest_path = os.path.join(font_dir, "Assistant-Regular.ttf")
            font_bold_dest_path = os.path.join(font_dir, "Assistant-Bold.ttf")

        parser = ConfigParser()
        parser.read(self.ui_config.user_config_path)

        if "UI" not in parser.sections():
            parser.add_section("UI")
        parser.set("UI", "HEADER_TEXT", header_text)
        parser.set("UI", "FOOTER_TEXT", footer_text)
        parser.set("UI", "FONT_NAME", font_name)
        parser.set("UI", "FONT_REGULAR_PATH", font_regular_dest_path)
        parser.set("UI", "FONT_BOLD_PATH", font_bold_dest_path)

        with open(self.ui_config.user_config_path, "w") as configfile:
            parser.write(configfile)

    async def _basic_token(
        self, password: AnyStr, username: AnyStr, jamf_url: Optional[AnyStr] = None
    ) -> bool:
        """
        Asynchronously retrieves a bearer token using basic auth. This function should not be used outside of initial setup/configuration to retrieve a bearer token as this is meant only to obtain client credentials for created API clients and roles.

        :param username: Username of admin Jamf Pro account for authentication. Not permanently stored, only used for initial token retrieval.
        :type username: AnyStr
        :param password: Password of admin Jamf Pro account. Not permanently stored, only used for initial token retrieval.
        :type password: AnyStr
        :param jamf_url: Jamf Server URL (same as `server_url` in `JamfClient` class)
        :type jamf_url: Optional[AnyStr]
        :raises: TokenFetchError or click.Abort if call is unauthorized or unsuccessful.
        :returns: True if basic token was generated, False if 401 encountered (SSO)
        """
        if jamf_url is None:
            self.jamf_url = jamf_url
        token_url = f"{jamf_url}/api/v1/auth/token"
        headers = {"accept": "application/json"}
        async with self.lock:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url=token_url, auth=aiohttp.BasicAuth(username, password), headers=headers
                ) as resp:
                    if resp.status == 401:
                        self.log.error(
                            f"Received 401 response trying to obtain access token with basic auth: {resp.status} - {await resp.text()}"
                        )
                        return False
                    elif resp.status != 200:
                        self.log.error(
                            f"Unsuccessful API call to retrieve access token with basic auth: {resp.status} - {await resp.text()}"
                        )
                        raise exceptions.TokenFetchError(
                            reason=f"{resp.status} - {await resp.text()}"
                        )
                    response = await resp.json()
                    if not response:
                        self.log.error(
                            "API call was successful, but response was empty. Exiting..."
                        )
                        click.echo(
                            click.style(
                                text="API response was empty. Unable to retrieve a token", fg="red"
                            ),
                            err=True,
                        )
                    self.token = response.get("token")
                    return True

    async def _create_roles(self, token: Optional[AnyStr] = None) -> bool:
        """
        Creates the necessary API roles using the provided token.

        :param token: The bearer token, defaults to None
        :type token: Optional[AnyStr]
        :return: True if roles were successfully created, False otherwise.
        :rtype: bool
        :raises aiohttp.ClientError: If there is an error making the HTTP request.
        """
        if token is None:
            token = self.token
        payload = {
            "displayName": "Patcher-Role",
            "privileges": [
                "Read Patch Management Software Titles",
                "Read Patch Policies",
                "Read Mobile Devices",
                "Read Mobile Device Inventory Collection",
                "Read Mobile Device Applications",
                "Read Patch Management Settings",
                "Create API Integrations",
                "Create API Roles",
                "Read API Integrations",
                "Read API Roles",
                "Update API Integrations",
                "Update API Roles",
                "Delete API Integrations",
                "Delete API Roles",
            ],
        }
        role_url = f"{self.jamf_url}/api/v1/api-roles"
        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.post(url=role_url, data=payload, headers=headers) as resp:
                resp.raise_for_status()
                return resp.status == 200

    async def _create_client(self) -> Tuple[AnyStr, AnyStr]:
        """
        Creates an API client and retrieves its client ID and client secret.

        :return: A tuple containing the client ID and client secret.
        :rtype: tuple[AnyStr, AnyStr]
        :raises aiohttp.ClientError: If there is an error making the HTTP request.
        """
        client_url = f"{self.jamf_url}/api/v1/api-integrations"
        payload = {
            "authorizationScopes": ["Patcher-Role"],
            "displayName": "Patcher-Client",
            "enabled": True,
            "accessTokenLifetimeSeconds": 1800,  # 30 minutes in seconds
        }
        headers = {"accept": "application/json", "Authorization": f"Bearer {self.token}"}
        async with aiohttp.ClientSession() as session:
            async with session.post(url=client_url, data=payload, headers=headers) as resp:
                resp.raise_for_status()
                client_response = await resp.json()
                if not client_response:
                    self.log.error(
                        f"API returned empty response during client creation. Status: {resp.status} - {await resp.text()}"
                    )
                client_id = client_response.get("clientId")
                integration_id = client_response.get("id")
        # Obtain client secret for client created
        secret_url = f"{self.jamf_url}/api/v1/api-integrations/{integration_id}/client-credentials"
        async with aiohttp.ClientSession() as session:
            async with session.post(url=secret_url, headers=headers) as resp:
                resp.raise_for_status()
                secret_response = await resp.json()
                if not secret_response:
                    self.log.error(
                        f"Unable to obtain client secret for Patcher client: {resp.status}"
                    )
                client_secret = secret_response.get("clientSecret")
        return client_id, client_secret

    async def first_run(self):
        """
        Similar to `launch` method, but triggered when SSO is being utilized by end-user.

        :raises SystemExit: If the user opts not to proceed with the setup.
        :raises exceptions.TokenFetchError: If there is an error fetching the token.
        """
        self.log.debug("Initializing first_run check")
        self._is_complete()
        if not self.completed:
            self.log.info("Detected first run has not been completed. Starting setup assistant...")
            self._greet()
            proceed = click.confirm("Ready to proceed?", default=False)
            if not proceed:
                click.echo("We'll be ready when you are!")
                self.log.info(f"User opted not to proceed with setup. User response was: {proceed}")
                sys.exit()
            else:
                api_url = click.prompt("Enter your Jamf Pro URL")
                api_client_id = click.prompt("Enter your API Client ID")
                api_client_secret = click.prompt("Enter your API Client Secret")

                # Store credentials
                self.config.set_credential("URL", api_url)
                self.config.set_credential("CLIENT_ID", api_client_id)
                self.config.set_credential("CLIENT_SECRET", api_client_secret)

                # Wait a short time to ensure creds are saved
                await sleep(3)

                # Generate bearer token and save it
                token = await self.token_manager.fetch_token()

                if token and isinstance(token, AccessToken):
                    self.token_manager.save_token(token)
                    self._setup_ui()
                    self._set_complete()
                else:
                    self.log.error("Failed to fetch a valid token!")
                    raise exceptions.TokenFetchError(reason="Token failed pydantic verification")
        else:
            self.log.debug("First run already completed.")

    async def launch(self):
        """
        Launches the setup assistant, prompting the user for necessary information and handling the setup process.

        :raises SystemExit: If the user opts not to proceed with the setup.
        :raises exceptions.TokenFetchError: If the API call to retrieve a token fails.
        :raises aiohttp.ClientError: If there is an error making the HTTP request.
        """
        self.log.debug("Detected first run has not been completed. Starting setup assistant...")
        self._greet()

        # Prompt end user to proceed when ready
        proceed = click.confirm("Ready to proceed?", default=False)

        if not proceed:
            click.echo("We'll be ready when you are!")
            self.log.info(f"User opted not to proceed with setup. User response was: {proceed}")
            sys.exit()

        self.jamf_url = click.prompt("Enter your Jamf Pro URL")
        username = click.prompt("Enter your Jamf Pro username")
        password = click.prompt("Enter your Jamf Pro password", hide_input=True)

        try:
            token_success = await self._basic_token(username=username, password=password)
            if not token_success:
                use_sso = click.confirm(
                    "We received a 401 response. Are you using SSO?", default=False
                )
                if use_sso:
                    await self.first_run()
                    return
                else:
                    token_success = await self._basic_token(username=username, password=password)
                    if not token_success:
                        click.echo(
                            click.style(
                                text="Unfortunately we received a 401 response again. Please verify your account does not use SSO.",
                                fg="red",
                            ),
                            err=True,
                        )
        except exceptions.TokenFetchError():
            click.echo(
                click.style(
                    text="Unfortunately we received an error trying to obtain a token. Please verify your account details and try again.",
                    fg="red",
                ),
                err=True,
            )

        role_created = await self._create_roles()
        if not role_created:
            self.log.error("Failed creating API roles. Exiting...")
            click.echo(click.style("Failed to create API roles.", fg="red"), err=True)

        client_id, client_secret = await self._create_client()
        if not client_id:
            click.echo(
                click.style(
                    text="Unable to create API client. Received invalid response.",
                    fg="red",
                ),
                err=True,
            )
        elif not client_secret:
            click.echo(
                click.style(
                    text=f"Unable to retrieve client secret. Received invalid response",
                    fg="red",
                ),
                err=True,
            )

        # Create ConfigManager, save credentials
        self.config.set_credential("URL", self.jamf_url)
        self.config.set_credential("CLIENT_ID", client_id)
        self.config.set_credential("CLIENT_SECRET", client_secret)

        # Wait a short time to ensure creds are saved
        await sleep(3)

        # Fetch Token and save if successful
        token = await self.token_manager.fetch_token()
        if token and isinstance(token, AccessToken):
            self.token_manager.save_token(token)
        else:
            self.log.error("Token failed validation. Notifying user and exiting...")
            click.echo(
                click.style(
                    text="Token retrieved failed verification and we're unable to proceed!",
                    fg="red",
                ),
                err=True,
            )

        # Setup UI Configuration
        self._setup_ui()

        # Set first run flag to True upon completion
        self._set_complete()

    async def reset(self):
        """
        Resets the setup process by setting _completed to False, updating the `first_run_done` flag in the plist file to False, and retriggers the function.
        """
        # Set completed to False
        self.completed = False

        # Update the plist file
        plist_data = {"first_run_done": False}
        try:
            with open(self.plist_path, "wb") as fp:
                plistlib.dump(plist_data, fp)
        except Exception as e:
            self.log.error(f"Error writing to plist file: {e}")
            raise exceptions.PlistError(path=self.plist_path)

        # Retrigger launch
        await self.launch()
