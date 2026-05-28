"""Shared base for schemas parsed from external upstream sources."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class UpstreamModel(BaseModel):
    """
    Base for models that mirror a third-party source's camelCase payload.

    Field names stay snake_case; ``to_camel`` auto-generates the camelCase wire
    alias (``bundle_id`` ⇄ ``bundleId``), so most fields need no explicit
    ``Field(alias=...)``. ``populate_by_name`` lets our code construct by either
    name, and unknown fields are ignored (Pydantic's default) so an upstream
    addition never breaks ingest.

    Deliberately a small twin of ``patcher.core.models.UpstreamModel`` rather
    than an import of it: importing the client package pulls pandas + keyring +
    the Jamf clients into the API process (a real cost on the 1 GB host), and
    the API is a separate, lightweight deployable.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")
