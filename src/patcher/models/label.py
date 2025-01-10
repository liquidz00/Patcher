from typing import Any, Dict, List, Optional

from pydantic import field_validator

from ..utils.exceptions import PatcherError
from . import Model


class Label(Model):
    name: str
    type: str
    expected_team_id: str
    installomator_label: str
    downloadURL: str
    curlOptions: Optional[List[str]] = None

    # NOTE: Planning on implementing these properties at a later time, commenting out for now.

    # Strongly recommended variables
    # appNewVersion: Optional[str] = None
    # versionKey: Optional[str] = None
    # packageID: Optional[str] = None
    # archiveName: Optional[str] = None
    # appName: Optional[str] = None
    # appCustomVersion: Optional[str] = None
    # targetDir: Optional[str] = "/Applications"
    # blockingProcesses: Optional[list[str]] = None
    # pkgName: Optional[str] = None
    # updateTool: Optional[str] = None
    # updateToolArguments: Optional[list[str]] = None
    # updateToolRunAsCurrentUser: Optional[bool] = False
    # CLIInstaller: Optional[str] = None
    # CLIArguments: Optional[list[str]] = None
    # installerTool: Optional[str] = None

    @classmethod
    @field_validator("type", mode="before")
    def validate_type(cls, v):
        allowed_types = ["dmg", "pkg", "zip", "tbz", "pkgInDmg", "pkgInZip", "appInDmgInZip"]
        if v not in allowed_types:
            raise PatcherError(f"Type must be one of {allowed_types}", type=v)
        return v

    @classmethod
    @field_validator("expectedTeamID", mode="before")
    def validate_team_id(cls, v):
        if len(v) != 10:
            raise PatcherError("expectedTeamID must be a 10-character string", team_id=v)
        return v

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **kwargs) -> "Label":
        """
        Creates a Label instance from a dictionary. Only includes keys that
        match the fields defined in the Label model.
        """
        field_names = cls.model_fields.keys()
        filtered_data = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered_data, **kwargs)
