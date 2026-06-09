"""ORM model for the AutoPkg recipe catalog source."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from patcher_api.db import Base


class AutopkgRecipe(Base):
    """
    A single AutoPkg recipe as listed in the ``autopkg/index`` repository's
    ``index.json`` file.

    AutoPkg is a recipe-based macOS app fetcher / packager. Each recipe is
    a processor pipeline (download, repackage, munki-import, jamf-upload,
    etc.) keyed by a reverse-DNS identifier. Patcher catalogs recipes as a
    **coverage indicator** only: their presence tells consumers "this app
    has AutoPkg automation available, here's where to find it." We do NOT
    execute recipes (AutoPkg itself is macOS-bound and Patcher's catalog is
    meant to be source-agnostic).

    A single app typically has multiple recipes across multiple parent /
    child chains (e.g. ``Firefox.download`` is parent to ``Firefox.munki``,
    ``Firefox.pkg``, ``Firefox.jss``). The ``name`` field is the matching
    key against ``apps`` (multiple recipes with the same ``name`` attach to
    the same app); ``shortname`` adds the recipe-type suffix
    (e.g. ``Spotify.munki``).
    """

    __tablename__ = "autopkg_recipes"

    identifier: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    shortname: Mapped[str | None] = mapped_column(String, nullable=True)
    repo: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    parent_identifier: Mapped[str | None] = mapped_column(String, nullable=True)
    inferred_type: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
