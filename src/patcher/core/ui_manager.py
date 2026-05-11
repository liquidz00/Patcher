import shutil
import ssl
from functools import cached_property
from pathlib import Path

import httpx
import truststore

from .exceptions import PatcherError
from .logger import LogMe
from .models.ui import UIConfigKeys, UIDefaults
from .plist_manager import PropertylistManager


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
        self.plist_manager = PropertylistManager()
        self.font_dir = self.plist_manager.plist_path.parent / "fonts"
        self._config = None  # Lazy-loaded

    @property
    def config(self) -> dict:
        """
        Retrieves the current UI configuration from property list, or creates default configuration.

        :return: Retrieved UI configuration settings or default config.
        :rtype: dict
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
    def config(self, value: dict):
        """
        Set specific UI configuration values with validation.

        :param value: dictionary containing configuration values to set.
        :type value: dict
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
        :rtype: bool
        """
        return all(font.exists() for font in self._get_font_paths().values())

    def _get_font_paths(self) -> dict[str, Path]:
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
        # truststore-backed SSL context mirrors BaseAPIClient's TLS handling
        # so font downloads work behind the same TLS-inspecting corporate
        # proxies that Jamf API calls do.
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        for font_type, url in self._FONT_URLS.items():
            dest = self._get_font_paths()[font_type]
            try:
                response = httpx.get(url, verify=ctx, follow_redirects=True, timeout=30.0)
                response.raise_for_status()
                dest.write_bytes(response.content)
                self.log.info(f"Font saved: {dest}")
            except (httpx.HTTPError, OSError) as e:
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
            UIConfigKeys.HEADER_COLOR.value: defaults.header_color,
        }

    def reset_config(self) -> bool:
        """
        Removes all existing UI settings from the property list file.

        This method is useful if the user wants to reconfigure the UI elements of PDF reports,
        such as header/footer text, font choices, and branding logo.

        See :ref:`Resetting Patcher <reset>` for more details.

        :return: ``True`` if the reset was successful.
        :rtype: bool
        """
        self.log.debug("Resetting UI-configuration settings.")
        try:
            return self.plist_manager.remove("UserInterfaceSettings")
        except PatcherError as e:
            self.log.error(f"Failed resetting UI-config settings. Details: {e}")
            return False

    def get_logo_path(self) -> str | None:
        """
        Retrieves the logo path from the UI configuration.

        :return: The logo path as a string if it exists, else None.
        :rtype: str | None
        """
        return self.config.get(UIConfigKeys.LOGO_PATH.value, "")
