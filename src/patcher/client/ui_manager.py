import asyncio
import plistlib
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import asyncclick as click
from PIL import Image

from ..utils import exceptions, logger
from . import BaseAPIClient


class UIConfigManager:
    """
    Manages the user interface configuration settings.

    This includes the management of header and footer text for exported PDFs,
    custom fonts, and font paths. The class also handles the downloading of
    default fonts if they are not already present.
    """

    REGULAR_FONT_URL = (
        "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Regular.ttf"
    )
    BOLD_FONT_URL = (
        "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Bold.ttf"
    )

    def __init__(self):
        """
        Initializes the UIConfigManager by loading the user interface configuration.
        """
        self.log = logger.LogMe(self.__class__.__name__)
        self.plist_path = (
            Path.home()
            / "Library"
            / "Application Support"
            / "Patcher"
            / "com.liquidzoo.patcher.plist"
        )
        self.font_dir = self.plist_path.parent / "fonts"
        self._fonts_saved = None
        self.api = BaseAPIClient()
        self.config = {}

        self.load_ui_config()

        if not self.plist_path.exists():
            asyncio.create_task(self.create_default_config())

    @property
    def fonts_present(self) -> bool:
        """
        Checks if the default fonts have already been downloaded.

        This property verifies if the required font files (regular and bold)
        are present in the expected directory.

        :return: ``True`` if the fonts are present, ``False`` otherwise.
        :rtype: bool
        """
        if self._fonts_saved is None:
            regular_font_path = self.font_dir / "Assistant-Regular.ttf"
            bold_font_path = self.font_dir / "Assistant-Bold.ttf"
            self._fonts_saved = regular_font_path.exists() and bold_font_path.exists()
        return self._fonts_saved

    def load_ui_config(self):
        """
        Loads the user interface configuration from the default and user configuration files.

        This method reads the Patcher property list file to retrieve the settings. If the
        property list file does not exist, it is created with default values.
        """
        if not self.plist_path.parent.exists():
            self.plist_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.plist_path.exists():
            self.config = {}  # Set to empty initially since async task will fill it later
        else:
            # Load configs
            plist_data = self._load_plist_file()
            self.config = plist_data.get("UI", {})
            # Ensure LOGO_PATH is initialized properly
            if "LOGO_PATH" not in self.config:
                self.config["LOGO_PATH"] = None

    async def download_font(self, url: str, dest_path: Path):
        """
        Downloads the Assistant font family from the specified URL to the given destination path.

        .. note:

            This API call is intentionally kept separate from the :class:`~patcher.client.api_client.ApiClient` class as
            the scope of this API call is solely for UI purposes.

        :param url: The URL to download the font from.
        :type url: str
        :param dest_path: The local path where the downloaded font should be saved.
        :type dest_path: str
        :raises exceptions.ShellCommandError: Raised if the font cannot be downloaded due to a network error or invalid response.
        """
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            self.log.error(f"Unable to create directory for fonts: {e}")
            raise exceptions.PatcherError("Could not create directory for Fonts.")

        command = ["/usr/bin/curl", "-sL", url, "-o", str(dest_path)]
        async with self.api.semaphore:
            try:
                await self.api.execute(command)
            except exceptions.ShellCommandError as e:
                self.log.error(f"Unable to download font from {url}: {e}")
                raise

    async def create_default_config(self):
        """
        This method writes default values for header text, footer text, and font paths
        into the property list file. It also ensures that the necessary fonts are
        downloaded if they are not already present.
        """
        default_config = {
            "HEADER_TEXT": "Default header text",
            "FOOTER_TEXT": "Default footer text",
            "FONT_NAME": "Assistant",
            "FONT_REGULAR_PATH": str(self.font_dir / "Assistant-Regular.ttf"),
            "FONT_BOLD_PATH": str(self.font_dir / "Assistant-Bold.ttf"),
        }

        # Ensure directory exists
        self.font_dir.mkdir(parents=True, exist_ok=True)

        # Download fonts if not already present
        if not self.fonts_present:
            await self.download_font(self.REGULAR_FONT_URL, self.font_dir / "Assistant-Regular.ttf")
            await self.download_font(self.BOLD_FONT_URL, self.font_dir / "Assistant-Bold.ttf")

        plist_data = self._load_plist_file()
        plist_data["UI"] = default_config
        self._write_plist_file(plist_data)

    def get_ui_config(self) -> Dict:
        """
        Retrieves the user interface configuration settings as a dictionary.

        :return: A dictionary containing UI configuration settings such as header text,
                 footer text, and font paths.
        :rtype: Dict
        """
        return self.config

    def get(self, key: str, fallback: str = None) -> str:
        """
        Retrieves a specific configuration value from the UI configuration.

        :param key: The key for the configuration value to retrieve.
        :type key: str
        :param fallback: The value to return if the key is not found. Defaults to ``None``.
        :type fallback: str, optional
        :return: The configuration value corresponding to the provided key, or the fallback value if the key is not found.
        :rtype: str
        """
        return self.get_ui_config().get(key, fallback)

    def reset_config(self) -> bool:
        """
        Resets the user interface settings in the property list file.

        This method removes all existing UI settings from the configuration file.
        It can be useful for restoring default values or clearing the configuration.

        :return: ``True`` if the reset was successful, ``False`` otherwise.
        :rtype: bool
        """
        try:
            plist_data = self._load_plist_file()
            if "UI" in plist_data:
                del plist_data["UI"]
                self._write_plist_file(plist_data)
                return True
            return False
        except Exception as e:
            self.log.error(f"An unexpected error occurred: {e}")
            return False

    def setup_ui(self):
        """
        Guides the user through configuring UI settings for PDF reports, including header/footer text and font choices.
        This function is used solely by the :class:`~patcher.client.setup.Setup` class during initial setup.

        :raises FileNotFoundError: IF the specified font file paths do not exist.
        """
        header_text = click.prompt("Enter the Header Text to use on PDF reports")
        footer_text = click.prompt("Enter the Footer Text to use on PDF reports")
        use_custom_font = click.confirm("Would you like to use a custom font?", default=False)
        use_logo = click.confirm(
            "Would you like to use a logo in your exported PDFs?", default=False
        )
        self.font_dir.mkdir(parents=True, exist_ok=True)

        font_name, font_regular_path, font_bold_path = self.configure_font(
            use_custom_font, self.font_dir
        )
        logo_path = self.configure_logo(use_logo)

        self.save_ui_config(
            header_text, footer_text, font_name, font_regular_path, font_bold_path, logo_path
        )

    @staticmethod
    def configure_font(use_custom_font: bool, font_dir: Path) -> Tuple[str, Path, Path]:
        """
        Configures the font settings based on user input.

        This method allows the user to specify a custom font or use the default provided by the application.
        The chosen fonts are copied to the appropriate directory for use in PDF report generation.

        This function is used solely by the :class:`~patcher.client.setup.Setup` class during initial setup.

        :param use_custom_font: Indicates whether to use a custom font.
        :type use_custom_font: bool
        :param font_dir: The directory to store the font files.
        :type font_dir: Union[str, Path]
        :return: A tuple containing the font name, regular font path, and bold font path.
        :rtype: Tuple[str, str, str]
        """
        if use_custom_font:
            font_name = click.prompt("Enter the custom font name", default="CustomFont")
            font_regular_src_path = Path(click.prompt("Enter the path to the regular font file"))
            font_bold_src_path = Path(click.prompt("Enter the path to the bold font file"))
            font_regular_dest_path = font_dir / font_regular_src_path.name
            font_bold_dest_path = font_dir / font_bold_src_path.name
            shutil.copy(font_regular_src_path, font_regular_dest_path)
            shutil.copy(font_bold_src_path, font_bold_dest_path)
        else:
            font_name = "Assistant"
            font_regular_dest_path = font_dir / "Assistant-Regular.ttf"
            font_bold_dest_path = font_dir / "Assistant-Bold.ttf"

        return font_name, font_regular_dest_path, font_bold_dest_path

    def configure_logo(self, use_logo: bool) -> Optional[str]:
        """
        Configures the logo file for PDF reports based on user input.

        If a logo file is specified, it is validated and copied to Patcher's Application Support directory.
        Similar to :meth:`~patcher.client.ui_manager.configure_font` this method is solely used in conjunction with the :class:`~patcher.client.setup.Setup` class.

        :param use_logo: Indicates whether or not to use a custom logo.
        :type use_logo: bool
        :return: The path to the saved logo file, or None if no logo is configured.
        :rtype: Optional[str]
        :raises exceptions.SetupError: If the provided logo path does not exist.
        :raises exceptions.PatcherError: If the provided logo fails pillow validation.
        """
        if not use_logo:
            self.log.info("Skipping logo configuration...")
            return None

        logo_dest_path = self.plist_path.parent / "logo.png"

        # Prompt for path
        logo_src_path = Path(click.prompt("Enter the path to the logo file"))
        if not logo_src_path.exists():
            self.log.error(f"Logo path does not exist: {logo_src_path}")
            raise exceptions.SetupError(
                f"{logo_src_path} does not exist, please check the path and try again."
            )

        # Validate file is an image
        try:
            with Image.open(logo_src_path) as img:
                img.verify()
        except (IOError, Image.UnidentifiedImageError) as e:
            self.log.error(f"Image validation failed for {logo_src_path}: {e}")
            raise exceptions.PatcherError(
                f"{logo_src_path} is not a valid image file. Please try again."
            )

        # Copy file
        try:
            shutil.copy(logo_src_path, logo_dest_path)
            self.log.info(f"Logo saved to {logo_dest_path}.")
        except Exception as e:
            self.log.error(f"Failed to copy logo to destination {logo_dest_path}: {e}")
            raise exceptions.PatcherError(
                f"Unable to save the logo file to {logo_dest_path}. Please try again."
            )

        # Save logo path in config
        self.config["LOGO_PATH"] = str(logo_dest_path)

        # Update plist file
        plist_data = self._load_plist_file()
        plist_data["UI"] = self.config
        self._write_plist_file(plist_data)

        return str(logo_dest_path)

    def save_ui_config(
        self,
        header_text: str,
        footer_text: str,
        font_name: str,
        font_regular_path: Union[str, Path],
        font_bold_path: Union[str, Path],
        logo_path: Optional[Union[str, Path]] = None,
    ):
        """
        Saves the UI configuration settings to the configuration file.
        This function is used solely by the :class:`~patcher.client.setup.Setup` class during initial setup.

        :param header_text: The header text for PDF reports.
        :type header_text: str
        :param footer_text: The footer text for PDF reports.
        :type footer_text: str
        :param font_name: The name of the font to use.
        :type font_name: str
        :param font_regular_path: The path to the regular font file.
        :type font_regular_path: Union[str, Path]
        :param font_bold_path: The path to the bold font file.
        :type font_bold_path: Union[str, Path]
        :param logo_path: The path to company/branding logo file.
        :type logo_path: Optional[Union[str, Path]], defaults to None.
        """
        # Load existing plist file if it exists
        plist_data = self._load_plist_file()

        plist_data["UI"] = {
            "HEADER_TEXT": header_text,
            "FOOTER_TEXT": footer_text,
            "FONT_NAME": font_name,
            "FONT_REGULAR_PATH": str(font_regular_path),
            "FONT_BOLD_PATH": str(font_bold_path),
            "LOGO_PATH": str(logo_path) if logo_path else None,
        }
        self._write_plist_file(plist_data)

    def get_logo_path(self) -> Union[str, None]:
        """
        Retrieves the logo path from the UI configuration.

        :return: The logo path as a string if it exists, else None.
        :rtype: Union[str, None]
        """
        return self.get("LOGO_PATH", None)

    def _load_plist_file(self) -> Dict:
        if self.plist_path.exists():
            with self.plist_path.open("rb") as plistfile:
                return plistlib.load(plistfile)
        return {}

    def _write_plist_file(self, plist_data: Dict):
        with self.plist_path.open("wb") as plistfile:
            plistlib.dump(plist_data, plistfile)
