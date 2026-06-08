"""
Pydantic schema for the Homebrew Cask API.

Models the subset of fields we care about. Extra fields are intentionally
ignored (`extra="ignore"`) so the schema stays resilient when Homebrew adds
new fields upstream.

Reference: https://formulae.brew.sh/docs/api/
"""

from pydantic import BaseModel, ConfigDict


class HomebrewCaskRecord(BaseModel):
    """The subset of Homebrew Cask API fields the catalog ingests."""

    model_config = ConfigDict(extra="ignore")

    token: str
    name: list[str]
    desc: str | None = None
    homepage: str | None = None
    url: str | None = None
    version: str | None = None
    sha256: str | None = None
    auto_updates: bool | None = None
    depends_on: dict | None = None
    artifacts: list[dict] = []
