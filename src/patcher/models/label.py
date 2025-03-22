from typing import Any, Dict, List, Union

from pydantic import Field, field_validator

from ..utils.ignored import IGNORED_LABELS
from . import Model


class Label(Model):
    """
    Represents an Installomator label.

    Installomator labels define metadata required for software installation using the Installomator tool. This includes information such as the download URL, expected Team ID, and type of installation package.

    For detailed reference on Installomator Labels, see :ref:`Installomator <installomator>` in the project docs, or visit the :ghwiki:`Labels reference <Installomator:Label Variables Reference>` in the Installomator wiki.

    :param name: The name of the Application the label is tied to (e.g., 'Google Chrome')
    :type name: :py:class:`str`
    :param type: The type of installation package.

            Allowed values:

            - ``dmg``
            - ``pkg``
            - ``zip``
            - ``tbz``
            - ``pkgInDmg``
            - ``pkgInZip``
            - ``appInDmgInZip``
            - ``appindmg``
            - ``bz2``

    :type type: :py:class:`str`
    :param expectedTeamID: The expected Team ID of the software publisher (must be a 10-character string).
    :type expectedTeamID: :py:class:`str`
    :param installomatorLabel: The label name of the software title (e.g., 'googlechromepkg')
    :type installomatorLabel: :py:class:`str`
    :param downloadURL: The URL from which the package can be downloaded.
    :type downloadURL: :py:class:`str`
    """

    name: str
    type: str
    expectedTeamID: str = Field(..., description="Expected Team ID (must be exactly 10 characters)")
    installomatorLabel: str  # fragmentName - ".sh"
    downloadURL: str

    def __str__(self) -> str:
        return f"Name: {self.name} Type: {self.type} Label: {self.installomatorLabel}"

    @field_validator("type", mode="before")
    def validate_type(cls, v: str) -> str:
        """
        Validates the ``type`` field to ensure it is a supported Installomator package type.

        :param v: The package type string
        :type v: :py:class:`str`
        :return: The validated package type or a fallback value if invalid.
        :rtype: :py:class:`str`
        """
        allowed_types = [
            "dmg",
            "pkg",
            "zip",
            "tbz",
            "pkgInDmg",
            "pkgInZip",
            "appInDmgInZip",
            "appindmg",
            "bz2",
        ]
        return v if v in allowed_types else f"UNSUPPORTED: {v}"

    @field_validator("expectedTeamID", mode="before")
    def validate_team_id(cls, v: str) -> str:
        """
        Validates the ``expectedTeamID`` field to ensure it is a 10-character identifier or an allowed Apple software string.

        :param v: The expected Team ID.
        :type v: :py:class:`str`
        :return: The validated Team ID or a fallback value if invalid.
        :rtype: :py:class:`str`
        """
        if v in "Software Update":
            return v  # Apple software/tools
        elif v in IGNORED_LABELS["teams"]:
            return "IGNORED_TEAM_ID"  # ignored team IDs
        elif len(v) != 10:
            return "INVALID_TEAM_ID"
        return v

    @field_validator("downloadURL", mode="before")
    def cast_download_url(cls, v: Union[str, List[str]]) -> str:
        """
        Ensures ``downloadURL`` is always stored as a string.
        If a list is provided, it joins the elements into a single string.

        :param v: The download URL, either as a string or list of strings.
        :type v: :py:obj:`~typing.Union` :py:class:`str` | :py:obj:`~typing.List`
        :return: The validated download URL as a string.
        :rtype: :py:class:`str`
        """
        if not v:
            return "UNKNOWN_URL"
        return " ".join(v) if isinstance(v, list) else str(v)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **kwargs) -> "Label":
        """
        Creates a ``Label`` instance from passed dictionary.

        Only includes keys that match the fields defined in the model.
        If a software title is in the ignore list, it returns ``None`` to skip processing.

        :param data: API response payload to parse for object creation.
        :type data: :py:obj:`~typing.Dict`
        :return: The configured ``Label`` object.
        :rtype: :class:`~patcher.models.label.Label`
        """
        if data.get("name") in IGNORED_LABELS["titles"]:
            return None  # Skip ignored

        # noinspection PyUnresolvedReferences
        field_names = cls.model_fields.keys()
        filtered_data = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered_data, **kwargs)
