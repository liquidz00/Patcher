import plistlib
from pathlib import Path
from typing import Any, Dict, Optional

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
        If the property list file does not exist, an empty dictionary is returned.

        If an error is raised trying to read the property list values, a debug message is logged
        and an empty dictionary is returned.
        """
        if not self.plist_path.exists():
            return {}
        try:
            with self.plist_path.open("rb") as plistfile:
                return plistlib.load(plistfile)
        except Exception as e:
            self.log.debug(
                f"Failed to load plist file. Returning an empty dictionary. Details: {e}"
            )
            return {}

    def _write_plist_file(self, plist_data: Dict) -> None:
        """Writes specified data to Patcher property list file."""
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

    def get_value(self, section: str, key: str) -> Optional[Any]:
        """
        Retrieves a specific value from the property list file.

        :param section: The section in the property list file to retrieve from.
        :type section: :py:class:`str`
        :param key: The key whose value should be retrieved.
        :type key: :py:class:`str`
        :return: The value of the specified key, or None if not found.
        :rtype: :py:obj:`~typing.Optional` [:py:obj:`~typing.Any`]
        """
        data = self._load_plist_file()
        return data.get(section, {}).get(key)

    def set_value(self, section: str, key: str, value: Any) -> None:
        """
        Sets a key-value pair in the property list file.

        :param section: The section in the property list to modify.
        :type section: :py:class:`str`
        :param key: The key to update.
        :type key: :py:class:`str`
        :param value: The value to set.
        :type value: :py:obj:`~typing.Any`
        """
        data = self._load_plist_file()
        if section not in data:
            data[section] = {}
        data[section][key] = value
        self._write_plist_file(data)

    def remove_key(self, section: str, key: str) -> None:
        """
        Removes a specific key from a specified section in the property list file.

        :param section: The section that contains the key to remove.
        :type section: :py:class:`str`
        :param key: The key to remove from the specified section.
        :type key: :py:class:`str`
        """
        data = self._load_plist_file()
        if section in data and key in data[section]:
            del data[section][key]
            self._write_plist_file(data)

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Retrieves an entire section from the property list file.

        :param section: The section to retrieve.
        :type section: :py:class:`str`
        :return: A dictionary containing all key-value pairs in the section, or an empty dict if the section does not exist.
        :rtype: :py:obj:`~typing.Dict` [:py:class:`str`, :py:obj:`~typing.Any`]
        """
        return self._load_plist_file().get(section, {})

    def set_section(self, section: str, values: Dict[str, Any]) -> None:
        """
        Replaces a section in the property list file with the passed values.

        :param section: The section of values to replace.
        :type section: :py:class:`str`
        :param values: The values to set within the section.
        :type values: :py:obj:`~typing.Dict` [:py:class:`str`, :py:obj:`~typing.Any`]
        """
        data = self._load_plist_file()
        data[section] = values
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
