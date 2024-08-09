import configparser
import os
import ssl
import urllib.request
from typing import AnyStr, Dict, Optional
from urllib.error import URLError

from ..utils import logger


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

    def __init__(self, custom_ca_file: Optional[str] = None):
        """
        Initializes the UIConfigManager by loading the user interface configuration.

        :param custom_ca_file: Optional path to a custom Certificate Authority (CA) file.
                               This is used for SSL verification during font downloads.
        :type custom_ca_file: Optional[str]
        """
        self.custom_ca_file = custom_ca_file
        self.config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
        self.user_config_dir = os.path.expanduser("~/Library/Application Support/Patcher")
        self.user_config_path = os.path.join(self.user_config_dir, "config.ini")
        self.font_dir = os.path.join(self.user_config_dir, "fonts")
        self.log = logger.LogMe(self.__class__.__name__)
        self._fonts_saved = None
        self.load_ui_config()

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
            regular_font_path = os.path.join(self.font_dir, "Assistant-Regular.ttf")
            bold_font_path = os.path.join(self.font_dir, "Assistant-Bold.ttf")
            self._fonts_saved = os.path.exists(regular_font_path) and os.path.exists(bold_font_path)
        return self._fonts_saved

    def download_font(self, url: AnyStr, dest_path: AnyStr):
        """
        Downloads the Assistant font family from the specified URL to the given destination path.

        If a custom CA file is provided, it is used to create an SSL context for the download.
        This method ensures the fonts are stored securely in the appropriate directory.

        :param url: The URL to download the font from.
        :type url: AnyStr
        :param dest_path: The local path where the downloaded font should be saved.
        :type dest_path: AnyStr
        :raises OSError: Raised if the font cannot be downloaded due to a network error or invalid response.
        """
        ssl_context = None
        if self.custom_ca_file:
            ssl_context = ssl.create_default_context(cafile=self.custom_ca_file)

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        try:
            with urllib.request.urlopen(url=url, context=ssl_context) as response:
                if response.status == 200:
                    with open(dest_path, "wb") as f:
                        f.write(response.read())
                else:
                    self.log.error(
                        f"Unable to download default fonts! Received status: {response.status}"
                    )
                    raise OSError("Unable to download default fonts.")
        except URLError as e:
            self.log.error(f"Unable to download default fonts: {e}")
            raise OSError(f"Unable to download default fonts: {e}")

    def create_default_config(self):
        """
        Creates the :ref:`config.ini <config_ini>` file with default settings for the user interface.

        This method writes default values for header text, footer text, and font paths
        into the configuration file. It also ensures that the necessary fonts are
        downloaded if they are not already present.
        """
        default_config = {
            "Settings": {"patcher_path": self.user_config_dir},
            "UI": {
                "HEADER_TEXT": "Default header text",
                "FOOTER_TEXT": "Default footer text",
                "FONT_NAME": "Assistant",
                "FONT_REGULAR_PATH": "${Settings:patcher_path}/fonts/Assistant-Regular.ttf",
                "FONT_BOLD_PATH": "${Settings:patcher_path}/fonts/Assistant-Bold.ttf",
            },
        }

        # Ensure directory exists
        os.makedirs(self.user_config_dir, exist_ok=True)

        # Download fonts if not already present
        if not self.fonts_present:
            self.download_font(
                self.REGULAR_FONT_URL, os.path.join(self.font_dir, "Assistant-Regular.ttf")
            )
            self.download_font(
                self.BOLD_FONT_URL, os.path.join(self.font_dir, "Assistant-Bold.ttf")
            )

        # Write default configuration
        with open(self.user_config_path, "w") as configfile:
            self.config.read_dict(default_config)
            self.config.write(configfile)

    def load_ui_config(self):
        """
        Loads the user interface configuration from the default and user configuration files.

        This method reads the ``config.ini`` file to retrieve the settings. If the
        configuration file does not exist, it is created with default values.
        """
        if not os.path.exists(self.user_config_path):
            self.create_default_config()

        # Load configs
        self.config.read(self.user_config_path)

    def get_ui_config(self) -> Dict:
        """
        Retrieves the user interface configuration settings as a dictionary.

        :return: A dictionary containing UI configuration settings such as header text,
                 footer text, and font paths.
        :rtype: Dict
        """
        return {
            "HEADER_TEXT": self.config.get("UI", "HEADER_TEXT"),
            "FOOTER_TEXT": self.config.get("UI", "FOOTER_TEXT", fallback="Default footer text"),
            "FONT_NAME": self.config.get("UI", "FONT_NAME", fallback="Assistant"),
            "FONT_REGULAR_PATH": self.config.get(
                "UI",
                "FONT_REGULAR_PATH",
                fallback=os.path.join(self.font_dir, "Assistant-Regular.ttf"),
            ),
            "FONT_BOLD_PATH": self.config.get(
                "UI",
                "FONT_BOLD_PATH",
                fallback=os.path.join(self.font_dir, "Assistant-Bold.ttf"),
            ),
        }

    def get(self, key: AnyStr, fallback: AnyStr = None) -> AnyStr:
        """
        Retrieves a specific configuration value from the UI configuration.

        :param key: The key for the configuration value to retrieve.
        :type key: AnyStr
        :param fallback: The value to return if the key is not found. Defaults to ``None``.
        :type fallback: AnyStr, optional
        :return: The configuration value corresponding to the provided key, or the fallback value if the key is not found.
        :rtype: AnyStr
        """
        return self.get_ui_config().get(key, fallback)

    def reset_config(self, config_path: Optional[AnyStr] = None) -> bool:
        """
        Resets the user interface settings in the ``config.ini`` file.

        This method removes all existing UI settings from the configuration file.
        It can be useful for restoring default values or clearing the configuration.

        :param config_path: The path of the configuration file to reset. If ``None``,
                            defaults to the current user's configuration path.
        :type config_path: Optional[AnyStr]
        :return: ``True`` if the reset was successful, ``False`` otherwise.
        :rtype: bool
        """
        config_path = config_path or self.user_config_path
        parser = configparser.ConfigParser()
        try:
            parser.read(config_path)
            if "UI" in parser:
                for key in parser["UI"]:
                    parser.remove_option("UI", key)
                with open(config_path, "w") as configfile:
                    parser.write(configfile)
                    return True
            else:
                return False
        except Exception as e:
            self.log.error(f"An unexpected error occurred: {e}")
            return False
