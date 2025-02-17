import shutil
from functools import cached_property
from pathlib import Path
from typing import Dict, Optional, Set, Tuple, Union

import asyncclick as click
from PIL import Image

from ..utils.exceptions import PatcherError, SetupError, ShellCommandError
from ..utils.logger import LogMe
from . import BaseAPIClient
from .plist_manager import PropertyListManager


class UIConfigManager:
    _REGULAR_FONT_URL = (
        "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Regular.ttf"
    )
    _BOLD_FONT_URL = (
        "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Bold.ttf"
    )

    # Config schema
    _CONFIG_SCHEMA: Set[str] = {
        "HEADER_TEXT",
        "FOOTER_TEXT",
        "FONT_NAME",
        "FONT_REGULAR_PATH",
        "FONT_BOLD_PATH",
        "LOGO_PATH",
    }

    def __init__(self):
        """
        Manages the user interface configuration settings.

        This includes the management of header and footer text for exported PDFs,
        custom fonts, font paths, and an optional branding logo. The class also handles
        the downloading of default fonts if they are not already present.
        """
        self.log = LogMe(self.__class__.__name__)
        self.plist_manager = PropertyListManager()
        self.api = BaseAPIClient()

        self.font_dir = self.plist_manager.plist_path.parent / "fonts"
        self._fonts_saved = None
        self._config = None  # Lazy-loaded

        self._load_ui_config()

    @property
    def config(self) -> Dict:
        """
        Retrieves the current UI configuration from property list, or creates default configuration.

        :return: Retrieved UI configuration settings or default config.
        :rtype: :py:obj:`~typing.Dict`
        """
        if self._config is None:
            self._load_ui_config()
        return self._config

    @config.setter
    def config(self, value: Dict = None, **kwargs):
        """
        Set specific UI configuration values with validation.

        :param value: Optional dictionary containing configuration values to set.
        :type value: :py:obj:`~typing.Dict` | None
        :param kwargs: Key-values to add to ``self._config``
        :type kwargs: :py:obj:`~typing.Dict` [:py:class:`str`, :py:obj:`~typing.Any`]
        :raises PatcherError: If any passed keyword arguments are not in the schema.
        """
        value = value or kwargs

        invalid_keys = set(value.keys()) - self._CONFIG_SCHEMA
        if invalid_keys:
            raise PatcherError(
                "Invalid configuration keys passed to Configuration setter.",
                keys=(", ".join(invalid_keys)),
            )

        self._config.update(value)
        self.log.debug(f"Updated configuration: {self._config}")
        self.plist_manager.set_section("UI", self._config)

    @cached_property
    def fonts_present(self) -> bool:
        """
        This property verifies if the required font files (regular and bold)
        are present in the expected directory.

        :return: ``True`` if the fonts are present.
        :rtype: :py:class:`bool`
        """
        regular, bold = self._get_default_font_paths()
        return regular.exists() and bold.exists()

    def _ensure_directory(self, path: Path) -> None:
        """Ensures the given directory exists and creates it if it does not."""
        self.log.debug(f"Validating {path} exists.")
        if not path.exists():
            self.log.info(f"Creating directory: {path}")
            try:
                path.mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                self.log.error(
                    f"Unable to create directory {path} due to PermissionError. Details: {e}"
                )
                raise PatcherError(
                    "Failed to create directory as expected due to PermissionError.",
                    path=path,
                    parent_path=path.parent,
                    error_msg=str(e),
                )

    def _load_ui_config(self) -> None:
        """Loads UI configuration from plist or creates default config if missing."""
        self._config = self.plist_manager.get_section("UI")
        if not self._config:
            self.log.info("No UI configuration found. Creating default UI settings.")
            self.create_default_config()

    def _download_font(self, url: str, dest_path: Path):
        """Downloads the Assistant font family from the specified URL to the given destination path."""
        command = ["/usr/bin/curl", "-sL", url, "-o", str(dest_path)]
        self.log.debug(f"Attempting to download default font family from {url} to {str(dest_path)}")
        try:
            self.api.execute_sync(command)
            self.log.info(f"Default fonts saved successfully to {dest_path}")
        except ShellCommandError as e:
            self.log.error(f"Unable to download font from {url}: {e}")
            raise PatcherError(
                "Failed to download default font family.",
                url=url,
                error_msg=str(e),
            )

    def _copy_file(self, src: Path, dest: Path):
        """Safely copy a file, handling exceptions."""
        try:
            shutil.copy(src, dest)
        except (OSError, PermissionError, shutil.SameFileError) as e:
            self.log.error(f"Failed to copy {src} to destination {dest}: {e}")
            raise PatcherError(
                "Failed to copy file as expected.",
                source=src,
                destination=dest,
                error_msg=str(e),
            )

    def _get_default_font_paths(self) -> Tuple[Path, Path]:
        """Returns default font paths as a tuple."""
        return (
            self.font_dir / "Assistant-Regular.ttf",
            self.font_dir / "Assistant-Bold.ttf",
        )

    def create_default_config(self):
        """
        This method writes default values for header text, footer text, font paths
        and optional branding logo into the property list file. It also ensures that the
        necessary fonts are downloaded if they are not already present.
        """
        self.log.debug("Attempting to create default configuration settings.")
        self._ensure_directory(self.font_dir)

        # Download fonts if not already present
        if not self.fonts_present:
            try:
                self._download_font(self._REGULAR_FONT_URL, self.font_dir / "Assistant-Regular.ttf")
                self._download_font(self._BOLD_FONT_URL, self.font_dir / "Assistant-Bold.ttf")
            except (PatcherError, ShellCommandError):
                raise  # Avoid chaining exception in this instance

        default_config = {
            "HEADER_TEXT": "Default header text",
            "FOOTER_TEXT": "Default footer text",
            "FONT_NAME": "Assistant",
            "FONT_REGULAR_PATH": str(self.font_dir / "Assistant-Regular.ttf"),
            "FONT_BOLD_PATH": str(self.font_dir / "Assistant-Bold.ttf"),
            "LOGO_PATH": "",
        }

        # Leverage setter
        self.plist_manager.set_section("UI", default_config)

    def reset_config(self) -> bool:
        """
        Removes all existing UI settings from the property list file.

        This method is useful if the user wants to reconfigure the UI elements of PDF reports,
        such as header/footer text, font choices, and branding logo.

        See :ref:`Resetting Patcher <reset>` for more details.

        :return: ``True`` if the reset was successful.
        :rtype: :py:class:`bool`
        """
        self.log.debug("Attempting to reset configuration settings.")
        return self.plist_manager.reset("UI")

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

        font_name, font_regular_path, font_bold_path = self.configure_font(use_custom_font)
        logo_path = self.configure_logo(use_logo)

        self.log.info("Gathered UI settings from user successfully.")
        self.save_ui_config(
            header_text, footer_text, font_name, font_regular_path, font_bold_path, logo_path
        )

    def configure_font(self, use_custom_font: bool) -> Tuple[str, Path, Path]:
        """
        Allows the user to specify a custom font or use the default provided by the application.
        The chosen fonts are copied to the appropriate directory for use in PDF report generation.

        .. note::
            This function is used solely by the :class:`~patcher.client.setup.Setup` class during initial setup.

        :param use_custom_font: Indicates whether to use a custom font.
        :type use_custom_font: :py:class:`bool`
        :return: A tuple containing the font name, regular font path, and bold font path.
        :rtype: :py:obj:`~typing.Tuple` [:py:class:`str`, :py:class:`~pathlib.Path`, :py:class:`~pathlib.Path`]
        """
        font_name = "Assistant"
        regular_font, bold_font = self._get_default_font_paths()

        if use_custom_font:
            self.log.debug("User chose to use custom font for PDF reports.")
            font_name = click.prompt("Enter the custom font name", default="CustomFont")
            regular_src = Path(click.prompt("Enter the path to the regular font file"))
            bold_src = Path(click.prompt("Enter the path to the bold font file"))
            regular_font = self.font_dir / regular_src.name
            bold_font = self.font_dir / bold_src.name

            self._copy_file(regular_src, regular_font)
            self._copy_file(bold_src, bold_font)

        self.log.info(f"Font information saved to {self.font_dir} successfully.")
        return font_name, regular_font, bold_font

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
        logo_src = Path(click.prompt("Enter the path to the logo file"))
        if not logo_src.exists():
            self.log.error(f"Logo path does not exist: {logo_src}")
            raise SetupError(
                "The specified logo path does not exist, please check the path and try again.",
                path=logo_src,
            )

        # Validate file is an image
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

        # Copy file
        logo_dest = self.plist_manager.plist_path.parent / "logo.png"
        self._copy_file(logo_src, logo_dest)
        self.config["LOGO_PATH"] = str(logo_dest)
        return str(logo_dest)

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
        self.log.debug("Attempting to save UI configuration settings.")
        plist_data = {
            "HEADER_TEXT": header_text,
            "FOOTER_TEXT": footer_text,
            "FONT_NAME": font_name,
            "FONT_REGULAR_PATH": str(font_regular_path),
            "FONT_BOLD_PATH": str(font_bold_path),
            "LOGO_PATH": str(logo_path) if logo_path else "",
        }
        self.config = plist_data
        self.log.info("Saved UI configuration settings successfully.")

    def get_logo_path(self) -> Union[str, None]:
        """
        Retrieves the logo path from the UI configuration.

        :return: The logo path as a string if it exists, else None.
        :rtype: :py:obj:`~typing.Union` :py:class:`str` | None]
        """
        return self.config.get("LOGO_PATH", "")
