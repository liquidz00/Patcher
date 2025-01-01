import asyncio
import plistlib
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import asyncclick as click
from PIL import Image

from ..utils.exceptions import PatcherError, SetupError, ShellCommandError
from ..utils.logger import LogMe
from . import BaseAPIClient


class UIConfigManager:
    REGULAR_FONT_URL = (
        "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Regular.ttf"
    )
    BOLD_FONT_URL = (
        "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Bold.ttf"
    )

    def __init__(self):
        """
        Manages the user interface configuration settings.

        This includes the management of header and footer text for exported PDFs,
        custom fonts, font paths, and an optional branding logo. The class also handles
        the downloading of default fonts if they are not already present.
        """
        self.log = LogMe(self.__class__.__name__)
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
        self.config = {}  # Set to empty initially since async task will fill it later

        self.load_ui_config()

        if not self.plist_path.exists():
            self.log.debug(
                f"Detected missing property list file ({self.plist_path}). Attempting to create default configuration."
            )
            asyncio.create_task(self.create_default_config())

    @property
    def fonts_present(self) -> bool:
        """
        This property verifies if the required font files (regular and bold)
        are present in the expected directory.

        :return: ``True`` if the fonts are present.
        :rtype: :py:class:`bool`
        """
        if self._fonts_saved is None:
            regular_font_path = self.font_dir / "Assistant-Regular.ttf"
            bold_font_path = self.font_dir / "Assistant-Bold.ttf"
            self._fonts_saved = regular_font_path.exists() and bold_font_path.exists()
        return self._fonts_saved

    def load_ui_config(self):
        """
        Reads the Patcher property list file to retrieve UI settings and loads them.
        If the property list file does not exist, it is created with default values.
        """
        if not self.plist_path.parent.exists():
            self.log.debug(
                "Attempting to create Patcher directory in user library Application Support directory."
            )
            self.plist_path.parent.mkdir(parents=True, exist_ok=True)

        # Load configs
        plist_data = self._load_plist_file()
        self.config = plist_data.get("UI", {})

        if "LOGO_PATH" not in self.config:  # Ensure LOGO_PATH is initialized properly
            self.config["LOGO_PATH"] = None

        self.log.info("Loaded UI configuration settings from property list successfully.")

    async def download_font(self, url: str, dest_path: Path):
        """
        Downloads the Assistant font family from the specified URL to the given destination path.

        .. note:
            This API call is intentionally kept separate from the :class:`~patcher.client.api_client.ApiClient` class as
            the scope of this API call is solely for UI purposes.

        :param url: The URL to download the font from.
        :type url: ;:py:class:`str`
        :param dest_path: The local path where the downloaded font should be saved.
        :type dest_path: :py:class:`~pathlib.Path`
        :raises ShellCommandError: Raised if the font cannot be downloaded due to a network error or invalid response.
        :raises PatcherError: If the destination path's parent cannot be created.
        """
        try:
            self.log.debug(
                f"Validating {dest_path.parent} exists. Will attempt to create if it does not exist already."
            )
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            self.log.info(f"Validated {dest_path.parent} successfully.")
        except PermissionError as e:
            self.log.error(f"Unable to create directory for fonts. Details: {e}")
            raise PatcherError(
                "Could not create directory for Fonts.",
                path=dest_path,
                parent_path=dest_path.parent,
                error_msg=str(e),
            )

        command = ["/usr/bin/curl", "-sL", url, "-o", str(dest_path)]
        async with self.api.semaphore:
            self.log.debug(
                f"Attempting to download default font family from {url} to {str(dest_path)}"
            )
            try:
                await self.api.execute(command)
                self.log.info(f"Default fonts saved successfully to {dest_path}")
            except ShellCommandError as e:
                self.log.error(f"Unable to download font from {url}: {e}")
                raise PatcherError(
                    "Failed to download default font family.",
                    url=url,
                    error_msg=str(e),
                )

    async def create_default_config(self):
        """
        This method writes default values for header text, footer text, font paths
        and optional branding logo into the property list file. It also ensures that the
        necessary fonts are downloaded if they are not already present.
        """
        self.log.debug("Attempting to create default configuration settings.")
        default_config = {
            "HEADER_TEXT": "Default header text",
            "FOOTER_TEXT": "Default footer text",
            "FONT_NAME": "Assistant",
            "FONT_REGULAR_PATH": str(self.font_dir / "Assistant-Regular.ttf"),
            "FONT_BOLD_PATH": str(self.font_dir / "Assistant-Bold.ttf"),
            "LOGO_PATH": None,
        }

        # Ensure directory exists
        self.font_dir.mkdir(parents=True, exist_ok=True)

        # Download fonts if not already present
        if not self.fonts_present:
            try:
                await self.download_font(
                    self.REGULAR_FONT_URL, self.font_dir / "Assistant-Regular.ttf"
                )
                await self.download_font(self.BOLD_FONT_URL, self.font_dir / "Assistant-Bold.ttf")
            except (PatcherError, ShellCommandError):
                raise

        plist_data = self._load_plist_file()
        plist_data["UI"] = default_config
        self._write_plist_file(plist_data)

    def get_ui_config(self) -> Dict:
        """
        Retrieves the user interface configuration settings as a dictionary.

        :return: Configuration settings such as header text, footer text, font paths, and branding logo.
        :rtype: :py:obj:`~typing.Dict`
        """
        self.log.debug("Attempting to retrieve UI Configuration settings.")
        return self.config

    def get(self, key: str, fallback: Optional[str] = None) -> str:
        """
        Retrieves a specific configuration value from the UI configuration.

        :param key: The key for the configuration value to retrieve.
        :type key: :py:class:`str`
        :param fallback: The value to return if the key is not found. Defaults to ``None``.
        :type fallback: :py:obj:`~typing.Optional` [:py:class:`str`]
        :return: The configuration value corresponding to the provided key, or the fallback value if the key is not found.
        :rtype: :py:class:`str`
        """
        return self.get_ui_config().get(key, fallback)

    def reset_config(self) -> bool:
        """
        Removes all existing UI settings from the property list file.

        This method is useful if the user wants to reconfigure the UI elements of PDF reports,
        such as header/footer text, font choices, and branding logo.

        :return: ``True`` if the reset was successful.
        :rtype: :py:class:`bool`
        """
        self.log.debug("Attempting to reset configuration settings.")
        try:
            plist_data = self._load_plist_file()
            if "UI" in plist_data:
                del plist_data["UI"]
                self._write_plist_file(plist_data)
                self.log.info("Configuration settings reset as expected.")
                return True
            return False
        except Exception as e:
            self.log.error(
                f"An unexpected error occurred when resetting UI settings in property list. Details: {e}"
            )
            return False

    def setup_ui(self):
        """
        Guides the user through configuring UI settings for PDF reports, including header/footer text,
        font choices, and an optional branding logo.

        .. note::
            This function is used solely by the :class:`~patcher.client.setup.Setup` class during initial setup.

        """
        self.log.debug("Prompting user for UI setup.")
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

        self.log.info("Gathered UI settings from user successfully.")
        self.save_ui_config(
            header_text, footer_text, font_name, font_regular_path, font_bold_path, logo_path
        )

    def configure_font(self, use_custom_font: bool, font_dir: Path) -> Tuple[str, Path, Path]:
        """
        Allows the user to specify a custom font or use the default provided by the application.
        The chosen fonts are copied to the appropriate directory for use in PDF report generation.

        If the specified font files cannot be copied to the passed ``font_dir``, the default fonts
        are used and a warning is logged.

        .. note::
            This function is used solely by the :class:`~patcher.client.setup.Setup` class during initial setup.

        :param use_custom_font: Indicates whether to use a custom font.
        :type use_custom_font: :py:class:`bool`
        :param font_dir: The directory to store the font files.
        :type font_dir: :py:class:`~pathlib.Path`
        :return: A tuple containing the font name, regular font path, and bold font path.
        :rtype: :py:obj:`~typing.Tuple` [:py:class:`str`, :py:class:`~pathlib.Path`, :py:class:`~pathlib.Path`]
        """
        if use_custom_font:
            self.log.debug(
                "User chose to use custom font for PDF reports. Prompting for font information."
            )
            font_name = click.prompt("Enter the custom font name", default="CustomFont")
            font_regular_src_path = Path(click.prompt("Enter the path to the regular font file"))
            font_bold_src_path = Path(click.prompt("Enter the path to the bold font file"))
            font_regular_dest_path = font_dir / font_regular_src_path.name
            font_bold_dest_path = font_dir / font_bold_src_path.name
            self.log.info("Font information gathered successfully.")
            try:
                self.log.debug(f"Attempting to copy font information to {font_dir}")
                shutil.copy(font_regular_src_path, font_regular_dest_path)
                shutil.copy(font_bold_src_path, font_bold_dest_path)
                self.log.info(f"Font information copied to {font_dir} successfully.")
            except (
                OSError,
                PermissionError,
                shutil.SameFileError,
                FileNotFoundError,
                TypeError,
            ) as e:
                self.log.warning(
                    f"Unable to copy custom font files to specified directory {font_dir}. Details: {e}"
                )
                font_name = "Assistant"
                font_regular_dest_path = font_dir / "Assistant-Regular.ttf"
                font_bold_dest_path = font_dir / "Assistant-Bold.ttf"
        else:
            self.log.info("Default font will be used for PDF reports.")
            font_name = "Assistant"
            font_regular_dest_path = font_dir / "Assistant-Regular.ttf"
            font_bold_dest_path = font_dir / "Assistant-Bold.ttf"

        return font_name, font_regular_dest_path, font_bold_dest_path

    def configure_logo(self, use_logo: bool) -> Optional[str]:
        """
        Configures the logo file for PDF reports based on user input.

        If a logo file is specified, it is validated and copied to Patcher's Application Support directory.
        Similar to :meth:`~patcher.client.ui_manager.UIConfigManager.configure_font` this method is
        solely used in conjunction with the :class:`~patcher.client.setup.Setup` class.

        :param use_logo: Indicates whether or not to use a custom logo.
        :type use_logo: :py:class:`bool`
        :return: The path to the saved logo file, or None if no logo is configured.
        :rtype: :py:obj:`~typing.Optional` [:py:class:`str`]
        :raises SetupError: If the provided logo path does not exist.
        :raises PatcherError: If the provided logo fails pillow validation.
        :raises PatcherError: If the logo file could not be copied to the destination path.
        """
        if not use_logo:
            self.log.info("Skipping logo configuration...")
            return None

        self.log.debug("Attempting to configure optional branding logo.")
        logo_dest_path = self.plist_path.parent / "logo.png"

        # Prompt for path
        logo_src_path = Path(click.prompt("Enter the path to the logo file"))
        if not logo_src_path.exists():
            self.log.error(f"Logo path does not exist: {logo_src_path}")
            raise SetupError(
                "The specified logo path does not exist, please check the path and try again.",
                path=logo_src_path,
            )

        # Validate file is an image
        try:
            with Image.open(logo_src_path) as img:
                img.verify()
            self.log.info(f"Logo file {logo_src_path} validated successfully.")
        except (IOError, Image.UnidentifiedImageError) as e:
            self.log.error(f"Image validation failed for {logo_src_path}: {e}")
            raise PatcherError(
                "The specified logo is not a valid image file. Please try again.",
                path=logo_src_path,
                error_msg=str(e),
            )

        # Copy file
        try:
            self.log.debug(f"Attempting to copy logo file to {logo_dest_path}")
            shutil.copy(logo_src_path, logo_dest_path)
            self.log.info(f"Logo saved to {logo_dest_path}.")
        except (
            FileNotFoundError,
            PermissionError,
            IsADirectoryError,
            OSError,
            shutil.SameFileError,
            TypeError,
        ) as e:
            self.log.error(f"Failed to copy logo to destination {logo_dest_path}: {e}")
            raise PatcherError(
                "Unable to save the logo file as expected. Please try again.",
                path=logo_dest_path,
                error_msg=str(e),
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

        .. note::
            This function is used solely by the :class:`~patcher.client.setup.Setup` class during initial setup.

        :param header_text: The header text for PDF reports.
        :type header_text: :py:class:`str`
        :param footer_text: The footer text for PDF reports.
        :type footer_text: :py:class:`str`
        :param font_name: The name of the font to use.
        :type font_name: :py:class:`str`
        :param font_regular_path: The path to the regular font file.
        :type font_regular_path: :py:obj:`~typing.Union` [:py:class:`str` | :py:class:`~pathlib.Path`]
        :param font_bold_path: The path to the bold font file.
        :type font_bold_path: :py:obj:`~typing.Union` [:py:class:`str` | :py:class:`~pathlib.Path`]
        :param logo_path: The path to company/branding logo file. Defaults to None.
        :type logo_path: :py:obj:`~typing.Optional` [:py:obj:`~typing.Union` [:py:class:`str` | :py:class:`~pathlib.Path`]]
        """
        # Load existing plist file if it exists
        plist_data = self._load_plist_file()

        self.log.debug("Attempting to save UI configuration settings.")
        plist_data["UI"] = {
            "HEADER_TEXT": header_text,
            "FOOTER_TEXT": footer_text,
            "FONT_NAME": font_name,
            "FONT_REGULAR_PATH": str(font_regular_path),
            "FONT_BOLD_PATH": str(font_bold_path),
            "LOGO_PATH": str(logo_path) if logo_path else None,
        }
        self._write_plist_file(plist_data)
        self.log.info("Saved UI configuration settings successfully.")

    def get_logo_path(self) -> Union[str, None]:
        """
        Retrieves the logo path from the UI configuration.

        :return: The logo path as a string if it exists, else None.
        :rtype: :py:obj:`~typing.Union` :py:class:`str` | None]
        """
        return self.get("LOGO_PATH", None)

    def _load_plist_file(self) -> Dict:
        """
        Reads values from Patcher property list file after verifying it exists.
        If the property list file does not exist, an empty dictionary is returned.

        If the property list file cannot be read, a warning is logged and an
        empty dictionary is returned.
        """
        if self.plist_path.exists():
            self.log.debug("Attempting to load property list file data.")
            with self.plist_path.open("rb") as plistfile:
                try:
                    plist_data = plistlib.load(plistfile)
                    self.log.info("Loaded property list data successfully.")
                    return plist_data
                except Exception as e:
                    self.log.warning(f"Unable to read property list file. Details: {e}")
                    return {}
        return {}

    def _write_plist_file(self, plist_data: Dict) -> None:
        """Writes specified data to Patcher property list file."""
        self.log.debug("Attempting to save passed plist_data to property list.")
        with self.plist_path.open("wb") as plistfile:
            try:
                plistlib.dump(plist_data, plistfile)
                self.log.info("Saved property list data successfully.")
            except Exception as e:
                self.log.error(f"Unable to write to property list. Details: {e}")
                raise PatcherError(
                    "Encountered an error trying to write to property list",
                    data=plist_data,
                    error_msg=str(e),
                )
