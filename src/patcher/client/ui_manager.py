import shutil
from functools import cached_property
from pathlib import Path
from typing import Dict, Union

import asyncclick as click
from PIL import Image

from ..models.ui import UIConfigKeys, UIDefaults
from ..utils.exceptions import PatcherError, SetupError, ShellCommandError
from ..utils.logger import LogMe
from . import BaseAPIClient
from .plist_manager import PropertyListManager


class UIConfigManager:
    _FONT_URLS = {
        "regular": "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Regular.ttf",
        "bold": "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Bold.ttf",
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
        self._config = None  # Lazy-loaded

    @property
    def config(self) -> Dict:
        """
        Retrieves the current UI configuration from property list, or creates default configuration.

        :return: Retrieved UI configuration settings or default config.
        :rtype: :py:obj:`~typing.Dict`
        """
        if self._config is None:
            saved_config = self.plist_manager.get("UserInterfaceSettings")
            if not saved_config:
                self.log.info("No UI configuration was found. Saving defaults.")
                self.create_default_config()
            else:
                self._config = saved_config
        return self._config

    @config.setter
    def config(self, value: Dict):
        """
        Set specific UI configuration values with validation.

        :param value: Dictionary containing configuration values to set.
        :type value: :py:obj:`~typing.Dict`
        :raises PatcherError: If any passed keyword arguments are not in the schema.
        """
        invalid_keys = value.keys() - {key.value for key in UIConfigKeys}
        if invalid_keys:
            raise PatcherError("Invalid configuration keys detected.", keys=", ".join(invalid_keys))

        if self._config is None:  # Ensure _config is initialized properly
            self._config = {}

        self._config.update(value)
        self.log.debug(f"Updated configuration: {self._config}")
        self.plist_manager.set("UserInterfaceSettings", self._config)

    @cached_property
    def fonts_present(self) -> bool:
        """
        This property verifies if the required font files (regular and bold)
        are present in the expected directory.

        :return: ``True`` if the fonts are present.
        :rtype: :py:class:`bool`
        """
        return all(font.exists() for font in self._get_font_paths().values())

    def _get_font_paths(self) -> Dict[str, Path]:
        """Returns default font paths as a tuple."""
        return {
            "regular": self.font_dir / "Assistant-Regular.ttf",
            "bold": self.font_dir / "Assistant-Bold.ttf",
        }

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

    def _download_fonts(self):
        """Downloads the Assistant font family to Patcher's font directory."""
        if self.fonts_present:
            return

        self._ensure_directory(self.font_dir)
        for font_type, url in self._FONT_URLS.items():
            dest = self._get_font_paths()[font_type]
            try:
                self.api.execute_sync(["/usr/bin/curl", "-sL", url, "-o", str(dest)])
                self.log.info(f"Font saved: {dest}")
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

    def create_default_config(self):
        """
        This method writes default values for header text, footer text, font paths
        and optional branding logo into the property list file. It also ensures that the
        necessary fonts are downloaded if they are not already present.
        """
        defaults = UIDefaults()
        self._download_fonts()

        self.config = {
            UIConfigKeys.HEADER.value: defaults.header_text,
            UIConfigKeys.FOOTER.value: defaults.footer_text,
            UIConfigKeys.FONT_NAME.value: defaults.font_name,
            UIConfigKeys.REG_FONT_PATH.value: str(self._get_font_paths()["regular"]),
            UIConfigKeys.BOLD_FONT_PATH.value: str(self._get_font_paths()["bold"]),
            UIConfigKeys.LOGO_PATH.value: defaults.logo_path,
        }

    def reset_config(self) -> bool:
        """
        Removes all existing UI settings from the property list file.

        This method is useful if the user wants to reconfigure the UI elements of PDF reports,
        such as header/footer text, font choices, and branding logo.

        See :ref:`Resetting Patcher <reset>` for more details.

        :return: ``True`` if the reset was successful.
        :rtype: :py:class:`bool`
        """
        self.log.debug("Resetting UI-configuration settings.")
        try:
            return self.plist_manager.remove("UserInterfaceSettings")
        except Exception as e:  # intentional
            self.log.error(f"Failed resetting UI-config settings. Details: {e}")
            return False

    def setup_ui(self):
        """
        Guides the user through configuring UI settings for PDF reports, including header/footer text,
        font choices, and an optional branding logo.

        .. note::
            This function is used solely by the :class:`~patcher.client.setup.Setup` class during initial setup.

        """
        self.log.debug("Prompting user for UI setup.")
        defaults = UIDefaults()
        self._download_fonts()

        settings = {
            UIConfigKeys.HEADER.value: click.prompt(
                "Enter Header Text for PDF reports",
                default=self.config.get(UIConfigKeys.HEADER.value, defaults.header_text),
                show_default=True,
            ),
            UIConfigKeys.FOOTER.value: click.prompt(
                "Enter Footer Text for PDF reports",
                default=self.config.get(UIConfigKeys.FOOTER.value, defaults.footer_text),
                show_default=True,
            ),
            UIConfigKeys.FONT_NAME.value: "Assistant",
            UIConfigKeys.REG_FONT_PATH.value: str(self._get_font_paths()["regular"]),
            UIConfigKeys.BOLD_FONT_PATH.value: str(self._get_font_paths()["bold"]),
            UIConfigKeys.LOGO_PATH.value: "",
        }

        if click.confirm("Would you like to use a custom font?", default=False):
            settings.update(self.configure_font())

        if click.confirm(
            "Would you like to use a custom logo in your exported PDF reports?", default=False
        ):
            settings[UIConfigKeys.LOGO_PATH.value] = self.configure_logo()

        self.config = settings

    def configure_font(self) -> Dict[str, str]:
        """
        Allows the user to specify a custom font or use the default provided by the application.
        The chosen fonts are copied to the appropriate directory for use in PDF report generation.

        :return: A dictionary containing the font name, regular font path, and bold font path.
        :rtype: :py:obj:`~typing.Dict` [:py:class:`str`, :py:class:`str`]
        """
        font_name = click.prompt("Enter custom font name", default="CustomFont")
        regular_src = Path(click.prompt("Enter the path to the regular font file"))
        bold_src = Path(click.prompt("Enter the path to the bold font file"))

        regular_dest, bold_dest = self._get_font_paths()["regular"], self._get_font_paths()["bold"]
        self._copy_file(regular_src, regular_dest)
        self._copy_file(bold_src, bold_dest)

        return {
            UIConfigKeys.FONT_NAME.value: font_name,
            UIConfigKeys.REG_FONT_PATH.value: str(regular_dest),
            UIConfigKeys.BOLD_FONT_PATH.value: str(bold_dest),
        }

    def configure_logo(self) -> str:
        """
        Configures the logo file for PDF reports based on user input.

        If a logo file is specified, it is validated and copied to Patcher's Application Support directory.
        Similar to :meth:`~patcher.client.ui_manager.UIConfigManager.configure_font` this method is
        solely used in conjunction with the :class:`~patcher.client.setup.Setup` class.

        :return: The path to the saved logo file, or None if no logo is configured.
        :rtype: :py:obj:`~typing.Optional` [:py:class:`str`]
        :raises SetupError: If the provided logo path does not exist.
        :raises PatcherError: If the provided logo fails pillow validation.
        :raises PatcherError: If the logo file could not be copied to the destination path.
        """
        logo_src = Path(click.prompt("Enter the path to the logo file"))
        if not logo_src.exists():
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

        logo_dest = self.plist_manager.plist_path.parent / "logo.png"
        self._copy_file(logo_src, logo_dest)
        return str(logo_dest)

    def get_logo_path(self) -> Union[str, None]:
        """
        Retrieves the logo path from the UI configuration.

        :return: The logo path as a string if it exists, else None.
        :rtype: :py:obj:`~typing.Union` :py:class:`str` | None]
        """
        return self.config.get(UIConfigKeys.LOGO_PATH.value, "")
