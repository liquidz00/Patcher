from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from patcher_api.db import Base


class HomebrewCask(Base):
    """
    A single Homebrew Cask record.

    Frequently-queried fields are exposed as real columns; the full upstream
    payload is preserved verbatim in ``raw`` so consumers can see Cask's
    native shape (per the same principle we use for source-detail payloads).

    Standalone table — no foreign key to ``apps`` yet. Cask records don't
    expose bundle_id; the join logic that links a cask to an ``apps`` row
    will be driven by the Installomator side once that ingestion lands.
    """

    __tablename__ = "homebrew_casks"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    desc: Mapped[str | None] = mapped_column(String, nullable=True)
    homepage: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    auto_updates: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
