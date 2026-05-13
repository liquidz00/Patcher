"""
Source-specific detail schemas.

Each source's native payload is intentionally typed as ``dict`` rather than a
projected/normalized model — consumers access the source's original shape
rather than something we've translated. This is what makes the API useful for
workflows like manually authoring Installomator labels from Homebrew Cask JSON
via Installomator's ``valuesfromarguments`` mechanism.
"""

from pydantic import BaseModel, HttpUrl


class InstallomatorSource(BaseModel):
    label_name: str
    label_url: HttpUrl
    raw: dict


class HomebrewCaskSource(BaseModel):
    token: str
    cask_json: dict


class AutopkgSource(BaseModel):
    recipe_name: str
    recipe_url: HttpUrl


class AppSources(BaseModel):
    installomator: InstallomatorSource | None = None
    homebrew_cask: HomebrewCaskSource | None = None
    autopkg: AutopkgSource | None = None
