import json
from enum import Enum
from pathlib import Path
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


class SetupType(str, Enum):
    """
    Defines the method of setup used for configuring Patcher.

    - ``STANDARD``: Prompts for Jamf Pro username/password and creates an API client.
    - ``SSO``: Prompts for an existing API client ID and secret.
    """

    STANDARD = "standard"
    SSO = "sso"


class SetupStage(str, Enum):
    """
    Represents the sequential stages in the setup process.

    Used to track progress and allow resuming setup from the last completed step.
    """

    NOT_STARTED = "not_started"
    API_CREATED = "api_created"
    HAS_TOKEN = "has_token"
    JAMFCLIENT_SAVED = "jamfclient_saved"
    COMPLETED = "completed"


class SetupStateManager:
    def __init__(self, state_path: Path):
        """
        Manages reading, writing, and resetting the current setup stage.

        This class is responsible for persisting setup progress to a JSON file,
        allowing the setup process to be resumed from the last known stage.

        :param state_path: Filesystem path to the JSON file used to persist setup stage.
        :type state_path: :py:obj:`~pathlib.Path`
        """
        self.state_path = state_path

    def load_stage(self) -> SetupStage:
        """
        Loads the saved setup stage from disk. If the file does not exist or is invalid,
        defaults to :attr:`~patcher.client.setup.SetupStage.NOT_STARTED`.

        Creates the stage file if it doesn't already exist.

        :return: The current saved setup stage.
        :rtype: :class:`~patcher.client.setup.SetupStage`
        """
        if not self.state_path.exists():
            self.state_path.touch()
            return SetupStage.NOT_STARTED
        try:
            with open(self.state_path, "r") as f:
                data = json.load(f)
                return SetupStage(data.get("setup_stage", SetupStage.NOT_STARTED))
        except Exception:  # intentional, using as fail-safe
            return SetupStage.NOT_STARTED

    def save_stage(self, stage: SetupStage) -> None:
        """
        Persists the provided setup stage to disk.

        Creates the parent directory if it does not exist.

        :param stage: The setup stage to persist.
        :type stage: :class:`~patcher.client.setup.SetupStage`
        """
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump({"setup_stage": stage.value}, f)

    def destroy(self) -> None:
        """
        Deletes the persisted setup stage file if it exists.
        """
        if self.state_path.exists():
            self.state_path.unlink()


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
        :param plist_manager: Handles read/write operations to project property list.
        :type plist_manager: :class:`~patcher.client.plist_manager.PropertyListManager`
        """
        self.config = config
        self.ui_config = ui_config
        self.plist_manager = plist_manager
        self.log = LogMe(self.__class__.__name__)
        self.animator = Animation()
        self._completed = None
        self.state_manager = SetupStateManager(
            Path.home() / "Library/Application Support/Patcher/.setup_stage.json"
        )
        self._stage = None
        self.stage_map = {
            SetupStage.NOT_STARTED: self.not_started,
            SetupStage.API_CREATED: self.api_created,
            SetupStage.HAS_TOKEN: self.has_token,
            SetupStage.JAMFCLIENT_SAVED: self.jamfclient_saved,
        }

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

    @property
    def stage(self) -> SetupStage:
        """
        Returns the current ``SetupStage`` value used to determine setup state.

        :return: The ``SetupStage`` value.
        :rtype: :class:`~patcher.client.setup.SetupStage`
        """
        if self._stage is None:
            self._stage = self.state_manager.load_stage()
        return self._stage

    @stage.setter
    def stage(self, value: SetupStage) -> None:
        """
        Assigns a ``SetupStage`` value to the stage property.

        :param value: The value to assign to ``self.stage``.
        :type value: :class:`~patcher.client.setup.SetupStage`
        """
        self._stage = value

    @staticmethod
    def _greet() -> None:
        """Displays the greeting and welcome messages."""
        click.echo(click.style(GREET, fg="cyan", bold=True))
        click.echo(click.style(WELCOME), nl=False)
        click.echo(click.style(DOC, fg="bright_magenta", bold=True))

    def _mark_completion(self, value: bool = False) -> None:
        """
        Updates the plist file to reflect the completion status of the setup.
        Additionally deletes the setup stage file if ``value`` is ``True``.
        """
        self.plist_manager.set("setup_completed", value)
        self._completed = value
        if value:
            self.state_manager.destroy()

    def _get_creds(self, include_token: bool = False) -> Dict:
        """Retrieves all stored credentials from keychain."""
        keys = ["URL", "CLIENT_ID", "CLIENT_SECRET"]
        if include_token:
            keys.extend(["TOKEN", "TOKEN_EXPIRATION"])
        return {key: self.config.get_credential(key) for key in keys}

    def _save_creds(self, creds: Dict) -> None:
        """Save gathered credentials to keychain."""
        for key, value in creds.items():
            self.config.set_credential(key, value)

    def prompt_credentials(self, setup_type: SetupType) -> Dict:
        """
        Prompt for credentials based on the credential type.

        :param setup_type: The ``SetupType`` of credentials to prompt for.
        :type setup_type: :class:`~patcher.client.setup.SetupType`
        :return: The credentials in dictionary form.
        :rtype: :py:obj:`~typing.Dict`
        """
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

    def validate_creds(
        self, creds: Dict, required_keys: Tuple[str, ...], setup_type: SetupType
    ) -> None:
        """
        Validates all required keys are present in the credentials.

        :param creds: Credentials to validate
        :type creds: :py:obj:`~typing.Dict`
        :param required_keys: Keys required to be present in passed credentials.
        :type required_keys: :py:obj:`~typing.Tuple` [:py:class:`str`, ...]
        :param setup_type: The ``SetupType`` to validate credentials against.
        :type setup_type: :class:`~patcher.client.setup.SetupType`
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
        Prompts user to enable or disable Installomator support.

        If enabled, assists in identifying :class:`~patcher.models.patch.PatchTitle` objects with Installomator support,
        used during :ref:`analyze <analyze>` commands.
        """
        use_installomator = click.confirm(
            "Would you like to enable Installomator support?", default=True
        )
        self.plist_manager.set("enable_installomator", use_installomator)

    async def get_token(
        self, setup_type: SetupType = SetupType.STANDARD, creds: Optional[Dict] = None
    ) -> Union[str, AccessToken]:
        """
        Fetches a Token (basic or ``AccessToken``) depending on setup type (Standard or SSO).

        :param setup_type: ``SetupType`` specified dictates which type of Token will be retrieved (basic or bearer).
        :type setup_type: :class:`~patcher.client.setup.SetupType`
        :param creds: If ``SetupType`` is "Standard", the user credentials needed to obtain a basic token.
        :type creds: :py:obj:`~typing.Optional` [:py:obj:`~typing.Dict`]
        :raises SetupError: If either type of Token could not be obtained.
        :return: For ``SetupType.STANDARD``, the basic token is returned. For ``SetupType.SSO``, the ``AccessToken`` object is returned.
        :rtype: :py:obj:`~typing.Union` [:py:class:`str`, :class:`~patcher.models.token.AccessToken`]
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

    async def create_api_client(self, basic_token: str, jamf_url: str) -> Tuple[str, str]:
        """
        Creates API Role and Client for standard setup types.

        :param basic_token: The basic token used for authorization in creating API Role and Client
        :type basic_token: :py:class:`str`
        :param jamf_url: The Jamf Pro instance URL to create API Role and Clients in.
        :type jamf_url: :py:class:`str`
        :raises SetupError: If either the API Role or API Client could not be created.
        :return: The client ID and client secret of the created API Client and Role.
        :rtype: :py:obj:`~typing.Tuple` [:py:class:`str`, :py:class:`str`]
        """
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

    async def not_started(self, animator: Animation, setup_type: SetupType) -> None:
        """
        Handles the initial setup stage based on the selected setup type.

        For ``STANDARD`` setup, prompts the user for username/password, creates a new API client,
        and saves credentials. For ``SSO``, stores the provided client credentials.

        :param animator: The animation instance to update messages.
        :type animator: :class:`~patcher.utils.animation.Animation`
        :param setup_type: The selected setup type (Standard or SSO).
        :type setup_type: :class:`~patcher.client.setup.SetupType`
        :raises SetupError: If credentials are missing or a token cannot be obtained.
        """
        creds = self.prompt_credentials(setup_type)
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
            self.state_manager.save_stage(SetupStage.API_CREATED)
            self.stage = SetupStage.API_CREATED
        elif setup_type == SetupType.SSO:
            self.validate_creds(creds, ("CLIENT_ID", "CLIENT_SECRET", "URL"), SetupType.SSO)
            await animator.update_msg("Saving credentials...")
            self._save_creds(creds)
            self.state_manager.save_stage(SetupStage.API_CREATED)
            self.stage = SetupStage.API_CREATED

    async def api_created(self, animator: Animation, _setup_type: SetupType) -> None:
        """
        Handles the stage after API credentials have been created or provided.

        Attempts to fetch and persist an ``AccessToken`` using stored credentials.

        :param animator: The animation instance to update messages.
        :type animator: :class:`~patcher.utils.animation.Animation`
        :param _setup_type: Placeholder to satisfy stage dispatch signature. Not used in this stage.
        :type _setup_type: :class:`~patcher.client.setup.SetupType`
        :raises SetupError: If an :class:`~patcher.models.token.AccessToken` cannot be retrieved
        """
        await animator.update_msg("Fetching AccessToken")
        client_creds = self._get_creds()
        await self.get_token(setup_type=SetupType.SSO, creds=client_creds)
        self.state_manager.save_stage(SetupStage.HAS_TOKEN)
        self.stage = SetupStage.HAS_TOKEN

    async def has_token(self, animator: Animation, _setup_type: SetupType) -> None:
        """
        Handles the stage after a token has been obtained.

        Uses stored credentials and token to instantiate and store a ``JamfClient`` object.

        :param animator: The animation instance to update messages.
        :type animator: :class:`~patcher.utils.animation.Animation`
        :param _setup_type: Placeholder to satisfy stage dispatch signature. Not used in this stage.
        :type _setup_type: :class:`~patcher.client.setup.SetupType`
        """
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
        self.state_manager.save_stage(SetupStage.JAMFCLIENT_SAVED)
        self.stage = SetupStage.JAMFCLIENT_SAVED

    async def jamfclient_saved(self, animator: Animation, _setup_type: SetupType) -> None:
        """
        Final stage in setup: configures user interface settings and marks setup as complete.

        :param animator: The animation instance to update messages.
        :type animator: :class:`~patcher.utils.animation.Animation`
        :param _setup_type: Placeholder to satisfy stage dispatch signature. Not used in this stage.
        :type _setup_type: :class:`~patcher.client.setup.SetupType`
        """
        await animator.stop()
        self.ui_config.setup_ui()
        self.state_manager.save_stage(SetupStage.COMPLETED)
        self.stage = SetupStage.COMPLETED
        self._mark_completion(value=True)

    async def start(self, animator: Optional[Animation] = None, fresh: bool = False) -> None:
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
        :param fresh: If ``True``, starts setup from scratch regardless of previous stage saved.
        :type fresh: :py:class:`bool`
        :raises SetupError: If a token could not be fetched, credentials are missing or setup could not be marked complete.
        """
        if self.completed:
            return

        animator = animator or self.animator
        setup_type_map = {1: SetupType.STANDARD, 2: SetupType.SSO}

        if fresh:
            self.stage = SetupStage.NOT_STARTED

        current_stage = self.stage

        # Prevent greeting from showing upon every invocation of setup assistant
        # Greeting should only show after reset or on first run
        if current_stage == SetupStage.COMPLETED:
            self.state_manager.destroy()  # Clean up stale state
        elif current_stage == SetupStage.NOT_STARTED:
            self._greet()
        elif not self.state_manager.state_path.exists():
            self._greet()

        choice = click.prompt(
            "Choose setup method (1: Standard setup, 2: SSO setup)", type=int, default=1
        )

        if choice in setup_type_map:
            while self.stage != SetupStage.COMPLETED:
                handler = self.stage_map.get(self.stage)
                if handler is None:
                    raise SetupError("Missing handler for saved stage", stage=self.stage)
                await handler(animator, setup_type_map[choice])
        else:
            click.echo(click.style("Invalid choice, please choose 1 or 2", fg="red"))
            await self.start()

    def reset_setup(self) -> bool:
        """
        Resets setup completion flag, removing the ``setup_completed`` key/value from the property list.

        This effectively marks Setup completion as False and will re-trigger the setup assistant.

        .. admonition:: Warning!
            :class: danger

            The Jamf API will return a ``400`` response if API Roles/Clients exist already in the Jamf instance specified.
            It is important to remove the API Role and Client objects before re-running the Setup assistant.

        :return: ``True`` if the Setup section in the property list file was removed.
        :rtype: :py:class:`bool`
        """
        self.log.debug("Attempting to reset setup.")
        success = self.plist_manager.remove("setup_completed")
        if success:
            self._completed = None
            self.log.info("Successfully reset setup.")
        return success
