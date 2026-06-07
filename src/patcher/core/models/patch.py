from datetime import datetime

from pydantic import ConfigDict, Field, field_validator, model_validator

from . import Model
from .cask import CaskMatch
from .label import Label


class PatchTitle(Model):
    """
    Represents patch software title information retrieved via API calls.

    :ivar title: The name of the patch title.
    :type title: str
    :ivar title_id: The ``softwareTitleId`` of the patch title from Jamf API response.
    :type title_id: str
    :ivar released: The release date of the patch title.
    :type released: str
    :ivar hosts_patched: The number of hosts that have applied the patch.
    :type hosts_patched: int
    :ivar missing_patch: The number of hosts missing the patch.
    :type missing_patch: int
    :ivar latest_version: The latest version available for the software title.
    :type latest_version: str
    :ivar completion_percent: The percentage of hosts that have applied the patch.
    :type completion_percent: float
    :ivar total_hosts: The total number of hosts.
    :type total_hosts: int
    :ivar install_label: The corresponding `InstallomatorClient <https://github.com/InstallomatorClient/InstallomatorClient>`_ label(s) if available.
    :ivar homebrew_cask: The corresponding `Homebrew Cask <https://github.com/Homebrew/homebrew-cask>`_ coverage stub(s) if available. Populated only when Homebrew matching is enabled; an independent signal from ``install_label``.
    :type homebrew_cask: list[:class:`~patcher.core.models.cask.CaskMatch`] | None
    """

    title: str
    title_id: str
    released: str
    hosts_patched: int
    missing_patch: int
    latest_version: str
    completion_percent: float = 0.0
    total_hosts: int = 0
    name_id: str | None = (
        None  # Jamf softwareTitleNameId; internal match key, stripped from PDF/Excel
    )
    install_label: list[Label] | None = []  # account for variants (e.g., zulujdk8, zulujdk9)
    homebrew_cask: list[CaskMatch] | None = []  # second matching dimension, opt-in

    def __str__(self):
        return f"{self.title} ({self.latest_version})"

    @field_validator("title_id")
    def cast_as_string(cls, value: int | str) -> str:
        """
        Ensures the ``title_id`` property is always a string, regardless of type in API response payload.

        :param value: The value of the ``title_id`` field.
        :type value: int | str
        :return: The value cast as a string.
        :rtype: str
        """
        return str(value)

    # Calculate completion percent via model validator
    @model_validator(mode="after")
    def calculate_completion_percent(self):
        """
        Calculates the completion percentage and total hosts of a :class:`~patcher.core.models.patch.PatchTitle` object based on hosts patched and missing patch.

        See :meth:`~patcher.clients.jamf.JamfClient.get_summaries`
        """
        # Calculate total hosts
        self.total_hosts = self.hosts_patched + self.missing_patch

        # Calculate completion percent
        if self.total_hosts > 0:
            self.completion_percent = round((self.hosts_patched / self.total_hosts) * 100, 2)
        else:
            self.completion_percent = 0.0

        return self


class PatchDevice(Model):
    """
    Represents device information from Jamf Pro patch management data.

    :ivar computer_name: The name of the computer.
    :type computer_name: str
    :ivar device_id: The unique device identifier from Jamf Pro.
    :type device_id: str
    :ivar username: The username associated with the device.
    :type username: str
    :ivar operating_system_version: The macOS version running on the device.
    :type operating_system_version: str
    :ivar last_contact_time: The last time the device contacted Jamf Pro.
    :type last_contact_time: datetime
    :ivar building_name: The building assignment for the device, if any.
    :type building_name: str | None
    :ivar department_name: The department assignment for the device, if any.
    :type department_name: str | None
    :ivar site_name: The site assignment for the device, if any.
    :type site_name: str | None
    :ivar version: The patch software version installed on the device.
    :type version: str
    """

    model_config = ConfigDict(populate_by_name=True)

    computer_name: str = Field(..., alias="computerName")
    device_id: str = Field(..., alias="deviceId")
    username: str
    operating_system_version: str = Field(..., alias="operatingSystemVersion")
    last_contact_time: datetime = Field(..., alias="lastContactTime")
    building_name: str | None = Field(default=None, alias="buildingName")
    department_name: str | None = Field(default=None, alias="departmentName")
    site_name: str | None = Field(default=None, alias="siteName")
    version: str

    def __str__(self) -> str:
        return f"{self.computer_name} ({self.username})"

    @field_validator("device_id")
    @classmethod
    def cast_as_string(cls, value: int | str) -> str:
        """
        Ensures the ``device_id`` property is always a string, regardless of type in API response payload.

        :param value: The value of the ``device_id`` field.
        :type value: int | str
        :return: The value cast as a string.
        :rtype: str
        """
        return str(value)

    @field_validator("building_name", "department_name", "site_name", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: str) -> str | None:
        """
        Converts empty strings to None for optional organizational fields.

        :param value: The value of the organizational field.
        :type value: str
        :return: None if empty string, otherwise the original value.
        :rtype: str | None
        """
        if value == "":
            return None
        return value
