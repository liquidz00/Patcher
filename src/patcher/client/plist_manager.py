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

        current_data = self._load_plist_file()
        if current_data == plist_data:
            self.log.debug("No changes detected in plist data. Skipping write operation.")
            return  # avoids unneccessary writes

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

    def needs_migration(self) -> bool:
        """
        Determines whether the plist file needs to be migrated.

        :return: True if old format is detected, False otherwise.
        :rtype: :py:class:`bool`
        """
        data = self._load_plist_file()
        return any(key in data for key in ["Setup", "UI", "Installomator"])

    def migrate_plist(self) -> None:
        """
        Modifies existing property list files in v1 format to v2 format.

        A backup file is created in the event migration fails so user settings are perserved.
        """
        data = self._load_plist_file()

        if not self.needs_migration():
            return

        self.log.info("Old property list format detected. Migrating...")
        backup_path = self.plist_path.with_suffix(".bak")
        shutil.copy(self.plist_path, backup_path)  # Save backup
        self.log.info(f"Backup property list file created: {backup_path}")

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
        try:
            self._write_plist_file(new_data)
            self.log.info("Property list migration completed.")
        except PatcherError:
            raise

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

    def set(self, key: str, value: Any, migration: bool = False) -> None:
        """
        Sets a key-value pair or replaces a section in the property list file.

        - If ``value`` is a dictionary and the existing key is also a dictionary, it merges them.
        - If ``value`` is a dictionary and the existing key is a primitive, it raises an error (unless ``migration=True``).
        - If ``value`` is a primitive and the existing key is a dictionary, it raises an error (unless ``migration=True``).
        - Otherwise, it stores the value as a top-level key.

        :param key: The section or top-level key in the property list.
        :type key: :py:class:`str`
        :param value: The value to assign. Can be a dictionary or a single value.
        :type value: :py:obj:`~typing.Any`
        :param migration: If True, allows type changes (dict → primitive or primitive → dict).
        :type migration: :py:class:`bool`
        """
        data = self._load_plist_file()

        if isinstance(value, dict):
            if key in data:
                if isinstance(data[key], dict):
                    data[key] = {**data.get(key, {}), **value}
                elif not migration:
                    raise PatcherError(
                        "Cannot overwrite non-dictionary key with a dictionary.",
                        key=key,
                        type=type(key),
                    )
                else:
                    data[key] = value  # migration mode enabled, overwrite
            else:
                data[key] = value
        else:
            if key in data:
                if isinstance(data[key], dict) and not migration:
                    raise PatcherError(
                        "Cannot overwrite dictionary key with a non-dictionary value.",
                        key=key,
                        type=type(key),
                    )
            data[key] = value

        self._write_plist_file(data)

    def remove(self, key: str, value: Optional[str] = None) -> bool:
        """
        Removes a key or a specific value from a key in the property list.

        - If ``value`` is None, the entire key (section) is removed.
        - If ``value`` is provided, only that specific value is removed from within the dictionary.

        :param key: The key (or section) to remove from the property list.
        :type key: :py:class:`str`
        :param value: The specific value to remove within the key. If None, removes the entire key.
        :type key: :py:obj:`~typing.Optional` [:py:class:`str`]
        :return: True if removal was successful, False otherwise.
        :rtype: :py:class:`bool`
        """
        data = self._load_plist_file()
        if key in data:
            if value:
                if isinstance(data[key], dict) and value in data[key]:
                    del data[key][value]
                    self.log.info(f"Removed value '{value}' from key '{key}'.")
                    self._write_plist_file(data)
                    return True
                else:
                    self.log.warning(
                        f"Value '{value}' not found in key '{key}'. No changes were made."
                    )
                    return True  # Treat as success
            else:
                del data[key]  # Remove key
                self.log.info(f"Removed key '{key}'.")
                self._write_plist_file(data)
                return True
        else:
            self.log.warning(f"Key '{key}' not found. No changes were made.")
            return True  # Treat as success

    def reset(self) -> bool:
        """
        Completely resets the property list by deleting the property list file.

        If the plist file exists, it is removed from disk. A new, empty plist will be created when values are next set.

        :return: True if reset was successful, False otherwise.
        :rtype: :py:class:`bool`
        """
        if self.plist_path.exists():
            try:
                self.plist_path.unlink()
                self.log.info(f"Property list file '{self.plist_path}' has been removed.")
                return True
            except Exception as e:  # using intentionally
                self.log.error(f"Failed to delete plist file. Details: {e}")
                return False
        else:
            self.log.warning(
                f"Property list file '{self.plist_path}' does not exist. Nothing to reset."
            )
            return True
