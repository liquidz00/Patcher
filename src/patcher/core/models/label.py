from typing import Any

from pydantic import Field, field_validator

from ..exceptions import PatcherError
from . import UpstreamModel


class Label(UpstreamModel):
    """
    Represents an Installomator label.

    Installomator labels define metadata required for software installation
    via the Installomator tool: a download URL, the expected Team ID for
    code-signature verification, the installer package type, and the label
    name used by the upstream catalog.

    Field names are Pythonic snake_case; upstream camelCase keys (as found
    in the raw ``.sh`` fragments) are accepted via Pydantic aliases. For
    detailed reference on Installomator labels, see :ref:`Installomator
    <installomator>` in the project docs, or visit the :ghwiki:`Labels
    reference <Installomator:Label Variables Reference>` in the
    Installomator wiki.

    :ivar name: The name of the application the label is tied to (e.g.,
        ``"Google Chrome"``).
    :type name: str
    :ivar type: The installer package type. Allowed values:

        - ``dmg``
        - ``pkg``
        - ``zip``
        - ``tbz``
        - ``pkgInDmg``
        - ``pkgInZip``
        - ``appInDmgInZip``
        - ``appindmg``
        - ``bz2``

    :type type: str
    :ivar expected_team_id: The expected Team ID of the software publisher
        (must be a 10-character string). Upstream alias: ``expectedTeamID``.
    :type expected_team_id: str
    :ivar installomator_label: The label name of the software title (e.g.,
        ``"googlechromepkg"``). Upstream alias: ``installomatorLabel``.
    :type installomator_label: str
    :ivar download_url: The URL from which the installer can be downloaded.
        Upstream alias: ``downloadURL``.
    :type download_url: str
    """

    name: str
    type: str | None = None
    expected_team_id: str | None = Field(
        default=None,
        alias="expectedTeamID",
        description="Expected Team ID (must be exactly 10 characters when present)",
    )
    # ``installomator_label`` rides on the to_camel alias generator from
    # ``UpstreamModel``, which produces ``installomatorLabel`` correctly.
    installomator_label: str  # fragmentName - ".sh"
    download_url: str | None = Field(default=None, alias="downloadURL")

    # TODO: implement the remaining Installomator label fields (appNewVersion,
    # versionKey, packageID, archiveName, blockingProcesses, pkgName, CLIInstaller, …).

    def __str__(self):
        return f"Name: {self.name} Type: {self.type} Label: {self.installomator_label}"

    @field_validator("type", mode="before")
    def validate_type(cls, v):
        if v is None:
            return None
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
        if v not in allowed_types:
            raise PatcherError(f"Type must be one of {allowed_types}", type=v)
        return v

    @field_validator("expected_team_id", mode="before")
    def validate_team_id(cls, v):
        if v is None:
            return None
        if v in "Software Update":
            return v  # Apple software/tools
        if len(v) != 10:
            raise PatcherError("expected_team_id must be a 10-character string", team_id=v)
        return v

    @classmethod
    def from_dict(cls, data: dict[str, Any], **kwargs) -> "Label":
        """
        Creates a ``Label`` instance from a dict whose keys are either the
        upstream camelCase names (``expectedTeamID``, ``downloadURL``,
        ``installomatorLabel``, ...) or the snake_case Python field names.

        Both forms are accepted thanks to ``populate_by_name=True`` on
        ``UpstreamModel``. Only keys that match
        a known field name or alias are forwarded to the constructor;
        unknown keys are silently dropped.

        :param data: Raw fragment data to parse for object creation.
        :type data: dict[str, Any]
        :return: The configured ``Label`` object.
        :rtype: :class:`~patcher.core.models.label.Label`
        """
        field_names = set(cls.model_fields.keys())
        aliases = {f.alias for f in cls.model_fields.values() if f.alias is not None}
        allowed = field_names | aliases
        filtered_data = {k: v for k, v in data.items() if k in allowed}
        return cls(**filtered_data, **kwargs)
