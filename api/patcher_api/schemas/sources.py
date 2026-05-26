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


class AutopkgRecipeEntry(BaseModel):
    """
    Single recipe attached to an app via the AutoPkg index.

    ``name`` and ``shortname`` are optional, mirroring the upstream index
    (and the :class:`~patcher_api.schemas.autopkg.AutopkgIndexEntry` ingest
    schema): shared-processor recipes carry ``name: null`` and some app
    recipes have no clean ``shortname``. The response must tolerate the
    ``None`` that stitch faithfully stored, or ``/apps/{slug}/sources``
    500s for any app whose matched recipes lack one.
    """

    identifier: str
    name: str | None = None
    shortname: str | None = None
    repo: str
    path: str
    parent_identifier: str | None = None
    inferred_type: str | None = None
    recipe_url: HttpUrl | None = None


class AutopkgSource(BaseModel):
    """
    All AutoPkg recipes matched to an app via the recipe index.

    AutoPkg coverage is multi-recipe by nature: a single app like Firefox
    typically has download, munki, pkg, jamf, and intune variants across
    multiple maintainer repos. Each match is preserved as a separate
    :class:`AutopkgRecipeEntry`.
    """

    recipes: list[AutopkgRecipeEntry]


class MasSource(BaseModel):
    bundle_id: str
    store_url: HttpUrl | None = None
    raw: dict


class JamfAppInstallerSource(BaseModel):
    """
    Coverage indicator for the Jamf App Installers catalog.

    Mirrors the three fields in the public HTML catalog. When a real Jamf
    Pro instance becomes available (the unlisted endpoint exposes
    bundle_id, version, download URL, and the Jamf Software Title ID),
    this schema grows additional optional fields.
    """

    title: str
    source: str
    host: str | None = None


class AppSources(BaseModel):
    installomator: InstallomatorSource | None = None
    homebrew_cask: HomebrewCaskSource | None = None
    autopkg: AutopkgSource | None = None
    mas: MasSource | None = None
    jamf_app_installer: JamfAppInstallerSource | None = None
