"""ORM model for the Mac App Store catalog source."""

from datetime import UTC, date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from patcher_api.db import Base


class MasApp(Base):
    """
    A Mac App Store app's metadata as reported by Apple's iTunes Search/Lookup
    API.

    ``bundle_id`` is the join key against the ``apps`` table. The MAS lookup
    is the storefront authority for apps published through the App Store, so
    when an app's bundle_id matches a record here, the catalog gains an
    additional source dimension with version + release metadata Apple
    publishes directly.

    No ``download_url`` column. MAS apps install via the Mac App Store, not
    a direct URL. ``store_url`` is the App Store deep link (an
    ``apps.apple.com`` URL) that downstream consumers can open in a browser
    or hand off to ``open`` on macOS to trigger an install.

    The full upstream payload is preserved verbatim in ``raw`` so consumers
    can see Apple's native shape (per the same principle we apply to
    Installomator labels and Homebrew Cask records).
    """

    __tablename__ = "mas_apps"

    bundle_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    release_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    store_url: Mapped[str | None] = mapped_column(String, nullable=True)
    minimum_os_version: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
