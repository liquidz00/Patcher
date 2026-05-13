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
    is informational, indexed for joins, and unique-when-not-null.
    """

    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    bundle_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    vendor: Mapped[str] = mapped_column(String, index=True)
    current_version: Mapped[str] = mapped_column(String)
    latest_release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    download_url: Mapped[str] = mapped_column(String)
    install_method: Mapped[str] = mapped_column(String)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    cves: Mapped[list[str]] = mapped_column(JSON, default=list)

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

    app: Mapped[App] = relationship(back_populates="source_detail")
