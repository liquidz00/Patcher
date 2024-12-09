from typing import Any

from pydantic import field_validator

from . import Model


class Label(Model):
    name: str
    type: str
    expected_team_id: str
    installomator_label: str

    # NOTE: Planning on implementing these properties at a later time, commenting out for now.

    # downloadURL: str = ""  # Not required for Patcher uses presently
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
    # curlOptions: Optional[list[str]] = None

    @classmethod
    @field_validator("type", mode="before")
    def validate_type(cls, v):
        allowed_types = ["dmg", "pkg", "zip", "tbz", "pkgInDmg", "pkgInZip", "appInDmgInZip"]
        if v not in allowed_types:
            raise ValueError(f"Type must be one of {allowed_types}")
        return v

    @classmethod
    @field_validator("expectedTeamID", mode="before")
    def validate_team_id(cls, v):
        if len(v) != 10:
            raise ValueError("expectedTeamID must be a 10-character string")
        return v

    @classmethod
    def from_dict(cls, data: dict[str, Any], **kwargs) -> "Label":
        """
        Creates a Label instance from a dictionary. Only includes keys that
        match the fields defined in the Label model.
        """
        field_names = cls.model_fields.keys()
        filtered_data = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered_data, **kwargs)
