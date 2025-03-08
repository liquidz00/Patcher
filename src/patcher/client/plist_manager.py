import plistlib
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ..models.ui import UIConfigKeys
from ..utils.exceptions import PatcherError
from ..utils.logger import LogMe


class PropertyListManager:
    def __init__(self):
        """
        Handles reading, writing, and managing configuration stored in Patcher's property list file (``self.plist_path``).

        A ``PatcherError`` will be raised in the event of directory creation failure or if an error occurs trying to write information to the property list.
        """
        self.plist_path = (
            Path.home() / "Library/Application Support/Patcher/com.liquidzoo.patcher.plist"
        )
        self.log = LogMe(self.__class__.__name__)
        self._ensure_directory(self.plist_path.parent)

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

    def _load_plist_file(self) -> Dict:
        """
        Reads values from Patcher property list file after verifying it exists.

        Empty dictionary will be returned if:
            - If the property list file does not exist
            - An error is encountered trying to read the property list values
        """
        if not self.plist_path.exists():
            self.log.debug(f"{self.plist_path} does not exist. Returning empty dictionary.")
            return {}
        try:
            with self.plist_path.open("rb") as plistfile:
                return plistlib.load(plistfile)
        except Exception as e:
            self.log.debug(
                f"Failed to load plist file. Returning an empty dictionary. Details: {e}"
            )
            return {}

    def _write_plist_file(self, plist_data: Dict[str, Any]) -> None:
        """Writes specified data to Patcher property list file."""
        if not isinstance(plist_data, dict):
            raise PatcherError("Invalid data type for property list. Expected dictionary.")

        self._ensure_directory(self.plist_path.parent)
        try:
            with self.plist_path.open("wb") as plistfile:
                plistlib.dump(plist_data, plistfile)
            self.log.info(f"Configuration saved to {self.plist_path}")
        except Exception as e:
            self.log.error(f"Failed to write plist file. Details: {e}")
            raise PatcherError(
                "Could not write to plist file.", path=self.plist_path, error_msg=str(e)
            )

    def migrate_plist(self) -> Dict[str, Any]:
        """
        #TODO

        :return: _description_
        :rtype: Dict[str, Any]
        """
        data = self._load_plist_file()
        if "Setup" in data or "UI" in data or "Installomator" in data:
            self.log.info("Old property list format detected. Migrating...")
            ui_dict = data.get("UI")
            new_data = {
                "setup_completed": data.get("Setup", {}).get("first_run_done", False),
                "enable_installomator": data.get("Installomator", {}).get("enabled", True),
                "enable_caching": True,
                "UserInterfaceSettings": {
                    UIConfigKeys.HEADER.value: ui_dict.get("HEADER_TEXT"),
                    UIConfigKeys.FOOTER.value: ui_dict.get("FOOTER_TEXT"),
                    UIConfigKeys.FONT_NAME.value: ui_dict.get("FONT_NAME"),
                    UIConfigKeys.REG_FONT_PATH.value: ui_dict.get("FONT_REGULAR_PATH"),
                    UIConfigKeys.BOLD_FONT_PATH.value: ui_dict.get("FONT_BOLD_PATH"),
                    UIConfigKeys.LOGO_PATH.value: ui_dict.get("LOGO_PATH"),
                },
            }

            backup_path = self.plist_path.with_suffix(".bak")
            shutil.copy(self.plist_path, backup_path)  # Save backup
            self.log.info(f"Backup property list file created: {backup_path}")

            self._write_plist_file(new_data)
            self.log.info("Property list migration completed.")

            return new_data

    def get(self, section: str, key: Optional[str] = None) -> Optional[Union[Dict[str, Any], Any]]:
        """
        Retrieves a value from the property list file.

        If a key is provided, its value will be returned. Otherwise, the section will be returned.

        :param section: The section in the property list file to retrieve from.
        :type section: :py:class:`str`
        :param key: The key whose value should be retrieved. If None, returns the entire section.
        :type key: :py:class:`str`
        :return: The value of the specified key, the full section, or None if not found.
        :rtype: :py:obj:`~typing.Optional` [:py:obj:`~typing.Any`]
        """
        data = self._load_plist_file()
        if section not in data:
            return None
        return data[section].get(key) if key else data[section]

    def set(
        self, section: str, key: Union[str, Dict[str, Any]], value: Optional[Any] = None
    ) -> None:
        """
        Sets a key-value pair or replaces a section in the property list file.

        :param section: The section in the property list to modify.
        :type section: :py:class:`str`
        :param key: If a dictionary, replaces the section. If a single value, updates a specific key.
        :type key: :py:obj:`~typing.Union` [:py:class:`str` | :py:obj:`~typing.Dict`]
        :param value: The value to assign if setting a single key.
        :type value: :py:obj:`~typing.Optional` [:py:obj:`~typing.Any`]
        """
        data = self._load_plist_file()

        if isinstance(key, dict):
            data[section] = key
        elif value is not None:
            data.setdefault(section, {})
            data[section][key] = value
        else:
            raise PatcherError(
                "If key is a string, a value must be provided.", key_type=type(key), received=value
            )

        self._write_plist_file(data)

    def remove(self, section: str, key: Optional[str] = None) -> None:
        """
        Removes a section or a specific key from the property list file.

        :param section: The section that contains the key to remove.
        :type section: :py:class:`str`
        :param key: The key to remove. If None, removes the entire section.
        :type key: :py:class:`str`
        """
        data = self._load_plist_file()
        if section in data:
            if key:
                data[section].pop(key, None)
            else:
                del data[section]
            self._write_plist_file(data)

    def reset(self, section: Optional[str] = None) -> bool:
        """
        Resets a specific section, or the entire property list file.

        :param section: The specific section to reset ("Setup", "UI", etc.). If none, resets everything.
        :type section: :py:obj:`~typing.Optional` [:py:class:`str`]
        :return: True if the reset was successful, False otherwise.
        :rtype: :py:class:`bool`
        """
        if section:
            data = self._load_plist_file()
            if section in data:
                del data[section]
                self.log.info(f"Reset section '{section}' in plist.")
                self._write_plist_file(data)
                return True
            else:
                self.log.warning(
                    f"Section '{section}' is not present in property list. Nothing to reset."
                )
                return True
        else:
            # Reset everything
            self.log.info("Resetting entire plist to default state.")
            self._write_plist_file({})
            return True
