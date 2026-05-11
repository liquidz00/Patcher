from typing import Any

from pydantic import Field, field_validator

from ..exceptions import PatcherError
from . import Model


class Label(Model):
    """
    Represents an InstallomatorClient label.

    InstallomatorClient labels define metadata required for software installation using the InstallomatorClient tool. This includes information such as the download URL, expected Team ID, and type of installation package.

    For detailed reference on InstallomatorClient Labels, see :ref:`InstallomatorClient <installomator>` in the project docs, or visit the :ghwiki:`Labels reference <InstallomatorClient:Label Variables Reference>` in the InstallomatorClient wiki.

    :param name: The name of the Application the label is tied to (e.g., 'Google Chrome')
    :type name: str
    :param type: The type of installation package.

            Allowed values:

            - ``dmg``
            - ``pkg``
            - ``zip``
            - ``tbz``
            - ``pkgInDmg``
            - ``pkgInZip``
            - ``appInDmgInZip``

    :type type: str
    :param expectedTeamID: The expected Team ID of the software publisher (must be a 10-character string).
    :type expectedTeamID: str
    :param installomatorLabel: The label name of the software title (e.g., 'googlechromepkg')
    :type installomatorLabel: str
    :param downloadURL: The URL from which the package can be downloaded.
    :type downloadURL: str
    """

    name: str
    type: str
    expectedTeamID: str = Field(..., description="Expected Team ID (must be exactly 10 characters)")
    installomatorLabel: str  # fragmentName - ".sh"
    downloadURL: str

    # NOTE: Planning on implementing these properties at a later time, commenting out for now.

    # Strongly recommended variables
    #   appNewVersion: Optional[str] = None
    #   versionKey: Optional[str] = None
    #   packageID: Optional[str] = None

    # Optional variables
    #   archiveName: Optional[str] = None
    #   appName: Optional[str] = None
    #   appCustomVersion: Optional[str] = None
    #   targetDir: Optional[str] = "/Applications"
    #   blockingProcesses: Optional[list[str]] = None
    #   pkgName: Optional[str] = None
    #   updateTool: Optional[str] = None
    #   updateToolArguments: Optional[list[str]] = None
    #   updateToolRunAsCurrentUser: Optional[bool] = False
    #   CLIInstaller: Optional[str] = None
    #   CLIArguments: Optional[list[str]] = None
    #   installerTool: Optional[str] = None
    #   curlOptions: Optional[list[str]] = None

    def __str__(self):
        return f"Name: {self.name} Type: {self.type} Label: {self.installomatorLabel}"

    @field_validator("type", mode="before")
    def validate_type(cls, v):
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

    @field_validator("expectedTeamID", mode="before")
    def validate_team_id(cls, v):
        if v in "Software Update":
            return v  # Apple software/tools
        if len(v) != 10:
            raise PatcherError("expectedTeamID must be a 10-character string", team_id=v)
        return v

    @classmethod
    def from_dict(cls, data: dict[str, Any], **kwargs) -> "Label":
        """
        Creates a ``Label`` instance from passed dictionary.

        Only includes keys that match the fields defined in the model.

        :param data: API response payload to parse for object creation.
        :type data: dict[str, Any]
        :return: The configured ``Label`` object.
        :rtype: :class:`~patcher.core.models.label.Label`
        """
        field_names = cls.model_fields.keys()
        filtered_data = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered_data, **kwargs)
