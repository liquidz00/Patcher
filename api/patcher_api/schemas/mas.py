"""
Pydantic schemas for Apple's iTunes Search/Lookup API.

Models the subset of fields we project into our ``MasApp`` table. Extra
fields are intentionally ignored (``extra="ignore"``) so the schema stays
resilient when Apple adds new ones upstream.

Reference: https://performance-partners.apple.com/search-api (the Apple
docs use "iTunes Search API" as the canonical product name; everywhere
*else* in the codebase we use "mas" / "Mac App Store" because the iTunes
brand is confusing to current readers).
"""

from pydantic import BaseModel, ConfigDict


class MasLookupRecord(BaseModel):
    """
    Single result from the lookup endpoint.

    Apple returns the fields camelCase as documented. We accept them verbatim
    here and project to snake_case at the model boundary, matching the
    pattern used for Homebrew Cask and Installomator records.
    """

    model_config = ConfigDict(extra="ignore")

    bundleId: str
    trackName: str
    version: str | None = None
    releaseDate: str | None = None
    releaseNotes: str | None = None
    trackViewUrl: str | None = None
    minimumOsVersion: str | None = None
    price: float | None = None
    kind: str | None = None
