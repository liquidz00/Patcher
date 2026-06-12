"""ORM models for the canonical app record and its per-source detail payloads."""

from datetime import date

from sqlalchemy import JSON, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from patcher_api.db import Base


class App(Base):
    """
    The canonical app record. One row per known macOS application.

    Uses a synthetic integer ``id`` as primary key because most apps in the
    catalog (those sourced from Installomator without a ``packageID``, or from
    Homebrew Cask without an Info.plist crawl) don't have a known bundle_id.
    ``slug`` is the URL-friendly public identifier used in routes; ``bundle_id``
    is informational and indexed for joins.

    ``bundle_id`` is intentionally **not** ``UNIQUE`` — multiple upstream
    Installomator labels can legitimately share a ``packageID`` (e.g. ``firefox``
    and ``firefoxpkg`` both pointing at ``org.mozilla.firefox``). Treating
    these as one app per (bundle_id) is a future deduplication concern.
    """

    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    bundle_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String)
    vendor: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    current_version: Mapped[str | None] = mapped_column(String, nullable=True)
    latest_release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    download_url: Mapped[str | None] = mapped_column(String, nullable=True)
    install_method: Mapped[str | None] = mapped_column(String, nullable=True)
    # Apple Team ID for code-signature checks; authoritatively from Installomator only.
    expected_team_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)

    source_detail: Mapped["AppSourceDetail | None"] = relationship(
        back_populates="app",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )


class AppSourceDetail(Base):
    """
    Per-source payloads for an app.

    Heterogeneous source shapes (Installomator labels, Homebrew Cask JSON,
    AutoPkg recipes) are stored as JSON columns rather than projected into a
    normalized schema — consumers see each source's native shape.
    """

    __tablename__ = "app_source_details"

    app_id: Mapped[int] = mapped_column(
        ForeignKey("apps.id", ondelete="CASCADE"),
        primary_key=True,
    )
    installomator: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    homebrew_cask: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    autopkg: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    jamf_app_installer: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    app: Mapped[App] = relationship(back_populates="source_detail")
