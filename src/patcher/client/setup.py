import configparser
import os
import plistlib
import shutil
import sys
from asyncio import Lock, sleep
from configparser import ConfigParser
from datetime import datetime, timedelta, timezone
from typing import AnyStr, Optional, Tuple

import aiohttp
import click

from ..models.jamf_client import ApiClient, ApiRole, JamfClient
from ..models.token import AccessToken
from ..utils import exceptions, logger
from ..utils.animation import Animation
from .config_manager import ConfigManager
from .ui_manager import UIConfigManager

# Welcome messages
GREET = "Thanks for downloading Patcher!\n"
WELCOME = """It looks like this is your first time using the tool. We will guide you through the initial setup to get you started.

The setup assistant will prompt you for your Jamf URL, your Jamf Pro username and your Jamf Pro password. Patcher ONLY uses this information to create the necessary API role and client on your behalf, your credentials are not stored whatsoever. Once generated, these client credentials (and generated bearer token) can be found in your keychain.

You will be prompted to enter in the header and footer text for PDF reports, should you choose to generate them. These can be configured later by modifying the 'config.ini' file in Patcher's Application Support directory stored in the user library.

"""
WIKI = "For more information, visit our project wiki: https://github.com/liquidz00/Patcher/wiki\n"


class Setup:
    """
    A class to handle the setup process for the Patcher tool.
    """

    def __init__(
        self,
        config: ConfigManager,
        ui_config: UIConfigManager,
    ):
        """
        Initializes the Setup class with the provided configuration and UI configuration.

        :param config: The configuration manager instance.
        :type config: ConfigManager
        :param ui_config: The UI configuration manager instance.
        :type ui_config: UIConfigManager
        """
        self.config = config
        self.ui_config = ui_config
        self.plist_path = os.path.expanduser(
            "~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist"
        )
        self.token = None
        self.jamf_url = None
        self.lock = Lock()
        self.log = logger.LogMe(self.__class__.__name__)
        self._completed = None

    @property
    def completed(self) -> bool:
        """
        Checks if the setup process has been completed.

        :return: True if setup completed, False otherwise.
        :rtype: bool
        """
        return self._completed if self._completed is not None else self._check_completion()

    def _check_completion(self):
        """
        Checks for the presence of the plist file to determine if setup has been completed.

        :return: True if setup has been completed, False otherwise.
        :rtype: bool
        :raises exceptions.PlistError: If there is an error reading the plist file.
        """
        self.log.debug("Checking for presence of .plist file")
        if os.path.exists(self.plist_path):
            try:
                with open(self.plist_path, "rb") as fp:
                    plist_data = plistlib.load(fp)
                    self._completed = plist_data.get("first_run_done", False)
            except Exception as e:
                self.log.error(f"Error reading plist file: {e}")
                print("PlistError is being raised")
                raise exceptions.PlistError(path=self.plist_path)
        else:
            self._completed = False
        return self._completed

    def _set_plist(self, value: bool = False):
        """
        Sets the passed value to the `first_run_done` key in the property list file in the user library.

        :param value: The value to set in the property list.
        :type value: bool
        :raises exceptions.PlistError: If there is an error writing to the plist file.
        """
        plist_data = {"first_run_done": value}
        try:
            os.makedirs(os.path.dirname(self.plist_path), exist_ok=True)
            with open(self.plist_path, "wb") as fp:
                plistlib.dump(plist_data, fp)
        except Exception as e:
            self.log.error(f"Error writing to plist file: {e}")
            raise exceptions.PlistError(path=self.plist_path)

    @staticmethod
    def _greet():
        """
        Displays the greeting and welcome messages.
        """
        click.echo(click.style(GREET, fg="cyan", bold=True))
        click.echo(click.style(WELCOME), nl=False)
        click.echo(click.style(WIKI, fg="bright_magenta", bold=True))

    def _setup_ui(self):
        """
        Prompts the user to enter UI configuration settings and saves them to the configuration file.

        :raises FileNotFoundError: IF the specified font file paths do not exist.
        """
        header_text = click.prompt("Enter the Header Text to use on PDF reports")
        footer_text = click.prompt("Enter the Footer Text to use on PDF reports")
        use_custom_font = click.confirm("Would you like to use a custom font?", default=False)
        font_dir = os.path.join(self.ui_config.user_config_dir, "fonts")
        os.makedirs(font_dir, exist_ok=True)

        font_name, font_regular_path, font_bold_path = self._configure_font(
            use_custom_font, font_dir
        )

        self._save_ui_config(header_text, footer_text, font_name, font_regular_path, font_bold_path)

    @staticmethod
    def _configure_font(use_custom_font: bool, font_dir: AnyStr) -> Tuple[AnyStr, AnyStr, AnyStr]:
        """
        Configures the font settings based on user input.

        :param use_custom_font: Indicates whether to use a custom font.
        :type use_custom_font: bool
        :param font_dir:  The directory to store the font files.
        :type font_dir: AnyStr
        :return: A tuple containing the font name, regular font path and bold font path.
        :rtype: Tuple[AnyStr, AnyStr, AnyStr]
        """
        if use_custom_font:
            font_name = click.prompt("Enter the custom font name", default="CustomFont")
            font_regular_src_path = click.prompt("Enter the path to the regular font file")
            font_bold_src_path = click.prompt("Enter the path to the bold font file")
            font_regular_dest_path = os.path.join(font_dir, os.path.basename(font_regular_src_path))
            font_bold_dest_path = os.path.join(font_dir, os.path.basename(font_bold_src_path))
            shutil.copy(font_regular_src_path, font_regular_dest_path)
            shutil.copy(font_bold_src_path, font_bold_dest_path)
        else:
            font_name = "Assistant"
            font_regular_dest_path = os.path.join(font_dir, "Assistant-Regular.ttf")
            font_bold_dest_path = os.path.join(font_dir, "Assistant-Bold.ttf")
        return font_name, font_regular_dest_path, font_bold_dest_path

    def _save_ui_config(
        self,
        header_text: AnyStr,
        footer_text: AnyStr,
        font_name: AnyStr,
        font_regular_path: AnyStr,
        font_bold_path: AnyStr,
    ):
        """
        Saves the UI configuration settings to the configuration file.

        :param header_text: The header text for PDF reports.
        :type header_text: AnyStr
        :param footer_text: The footer text for PDF reports.
        :type footer_text: AnyStr
        :param font_name: The name of the font to use.
        :type font_name: AnyStr
        :param font_regular_path: The path to the regular font file.
        :type font_regular_path: AnyStr
        :param font_bold_path: The path to the bold font file.
        :type font_bold_path: AnyStr
        """
        parser = ConfigParser(interpolation=configparser.ExtendedInterpolation())
        parser.read(self.ui_config.user_config_path)

        if "UI" not in parser.sections():
            parser.add_section("UI")
        parser.set("UI", "HEADER_TEXT", header_text)
        parser.set("UI", "FOOTER_TEXT", footer_text)
        parser.set("UI", "FONT_NAME", font_name)
        parser.set("UI", "FONT_REGULAR_PATH", font_regular_path)
        parser.set("UI", "FONT_BOLD_PATH", font_bold_path)

        with open(self.ui_config.user_config_path, "w") as configfile:
            parser.write(configfile)

    async def _basic_token(
        self, password: AnyStr, username: AnyStr, jamf_url: Optional[AnyStr] = None
    ) -> bool:
        """
        Asynchronously retrieves a bearer token using basic auth.

        This function should not be used outside of initial setup/configuration to retrieve a bearer token as this is meant only to obtain client credentials for created API clients and roles.

        :param username: Username of admin Jamf Pro account for authentication. Not permanently stored, only used for initial token retrieval.
        :type username: AnyStr
        :param password: Password of admin Jamf Pro account. Not permanently stored, only used for initial token retrieval.
        :type password: AnyStr
        :param jamf_url: Jamf Server URL (same as `server_url` in `JamfClient` class)
        :type jamf_url: Optional[AnyStr]
        :raises exceptions.TokenFetchError: If the call is unauthorized or unsuccessful.
        :returns: True if basic token was generated, False if 401 encountered (SSO)
        :rtype: bool
        """
        self.jamf_url = jamf_url or self.jamf_url
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
        token = token or self.token
        role = ApiRole()
        payload = {
            "displayName": role.display_name,
            "privileges": role.privileges,
        }
        role_url = f"{self.jamf_url}/api/v1/api-roles"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url=role_url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                return resp.status == 200

    async def _create_client(self, token: Optional[AnyStr] = None) -> Tuple[AnyStr, AnyStr]:
        """
        Creates an API client and retrieves its client ID and client secret.

        :return: A tuple containing the client ID and client secret.
        :rtype: tuple[AnyStr, AnyStr]
        :raises aiohttp.ClientError: If there is an error making the HTTP request.
        """
        token = token or self.token
        client = ApiClient()
        client_url = f"{self.jamf_url}/api/v1/api-integrations"
        payload = {
            "authorizationScopes": client.auth_scopes,
            "displayName": client.display_name,
            "enabled": client.enabled,
            "accessTokenLifetimeSeconds": client.token_lifetime,  # 30 minutes in seconds
        }
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url=client_url, json=payload, headers=headers) as resp:
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

    async def _fetch_bearer(
        self, url: AnyStr, client_id: AnyStr, client_secret: AnyStr
    ) -> Optional[AccessToken]:
        """
        Fetches a bearer token using client credentials.

        :param url: The URL to fetch the bearer token from.
        :type url: AnyStr
        :param client_id: The client ID.
        :type client_id: AnyStr
        :param client_secret: The client secret.
        :type client_secret: AnyStr
        :return: An AccessToken object if successful, None otherwise.
        :rtype: Optional[AccessToken]
        """
        async with self.lock:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "client_id": client_id,
                    "grant_type": "client_credentials",
                    "client_secret": client_secret,
                }
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                async with session.post(
                    url=f"{url}/api/oauth/token", data=payload, headers=headers
                ) as resp:
                    resp.raise_for_status()
                    try:
                        json_response = await resp.json()
                    except aiohttp.ClientResponseError as e:
                        self.log.error(f"Failed to fetch a token: {e}")
                        return None

                    bearer_token = json_response.get("access_token")
                    expires_in = json_response.get("expires_in", 0)

                    if not isinstance(bearer_token, str) or expires_in <= 0:
                        self.log.error("Received invalid token response")
                        return None

                    expiration = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    access_token = AccessToken(token=bearer_token, expires=expiration)
                    return access_token

    async def first_run(self):
        """
        Similar to `launch` method, but triggered when SSO is being utilized by end-user.

        :raises SystemExit: If the user opts not to proceed with the setup.
        :raises exceptions.TokenFetchError: If there is an error fetching the token.
        """
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
                token = await self._fetch_bearer(
                    url=api_url, client_id=api_client_id, client_secret=api_client_secret
                )

                if token:
                    jamf_client = JamfClient(
                        client_id=api_client_id,
                        client_secret=api_client_secret,
                        server=api_url,
                        token=token,
                    )
                    self.config.create_client(jamf_client)
                    self._setup_ui()
                    self._set_plist(value=True)
                    self._completed = True
                else:
                    self.log.error("Failed to fetch a valid token!")
                    raise exceptions.TokenFetchError(reason="Token failed pydantic verification")
        else:
            self.log.debug("First run already completed.")

    async def launch(self, animator: Animation, show_msg: bool = True, confirm: bool = True):
        """
        Launches the setup assistant, prompting the user for necessary information and handling the setup process.

        :param animator: The animation instance to update messages.
        :type animator: Animation
        :param show_msg: Whether to show the greeting message.
        :type show_msg: bool
        :param confirm: Whether to ask for user confirmation before proceeding.
        :type confirm: bool
        :raises SystemExit: If the user opts not to proceed with the setup.
        :raises exceptions.TokenFetchError: If the API call to retrieve a token fails.
        :raises aiohttp.ClientError: If there is an error making the HTTP request.
        """
        if not self.completed:
            self.log.debug("Detected first run has not been completed. Starting setup assistant...")
            if show_msg:
                self._greet()

            if confirm:
                # Prompt end user to proceed when ready
                proceed = click.confirm("Ready to proceed?", default=False)

                if not proceed:
                    click.echo("We'll be ready when you are!")
                    self.log.info(
                        f"User opted not to proceed with setup. User response was: {proceed}"
                    )
                    sys.exit()

            self.jamf_url = click.prompt("Enter your Jamf Pro URL")
            username = click.prompt("Enter your Jamf Pro username")
            password = click.prompt("Enter your Jamf Pro password", hide_input=True)

            await animator.update_msg("Retrieving basic token")
            try:
                token_success = await self._basic_token(
                    username=username, password=password, jamf_url=self.jamf_url
                )
                if not token_success:
                    use_sso = click.confirm(
                        "We received a 401 response. Are you using SSO?", default=False
                    )
                    if use_sso:
                        await self.first_run()
                        return
                    else:
                        token_success = await self._basic_token(
                            username=username, password=password
                        )
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

            await animator.update_msg("Creating roles")
            role_created = await self._create_roles()
            if not role_created:
                self.log.error("Failed creating API roles. Exiting...")
                click.echo(click.style("Failed to create API roles.", fg="red"), err=True)

            await animator.update_msg("Creating client")
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

            await animator.update_msg("Saving URL and client credentials")
            # Create ConfigManager, save credentials
            self.config.set_credential("URL", self.jamf_url)
            self.config.set_credential("CLIENT_ID", client_id)
            self.config.set_credential("CLIENT_SECRET", client_secret)

            # Wait a short time to ensure creds are saved
            await sleep(3)

            await animator.update_msg("Fetching bearer token")
            # Fetch Token and save if successful
            token = await self._fetch_bearer(
                url=self.jamf_url, client_id=client_id, client_secret=client_secret
            )
            if token:
                # Create JamfClient object with all credentials
                jamf_client = JamfClient(
                    client_id=client_id,
                    client_secret=client_secret,
                    server=self.jamf_url,
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
            self._setup_ui()

            # Set first run flag to True upon completion
            self._set_plist(value=True)
            self._completed = True

    async def reset(self, animator: Animation):
        """
        Resets the user interface elements of PDF reports by modifying config.ini

        :param animator: The animation instance to update messages.
        :type animator: Animation
        """
        # Clear exisiting UI configuration
        reset_config = self.ui_config.reset_config()
        if not reset_config:
            self.log.error("Encountered an issue resetting elements in config.ini.")
            raise OSError("The UI element configuration file could not be reset as expected.")
        else:
            self._setup_ui()
