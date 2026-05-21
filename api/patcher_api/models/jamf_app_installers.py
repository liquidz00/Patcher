from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from patcher_api.db import Base


class JamfAppInstaller(Base):
    """
    A single title from the Jamf App Installers public catalog.

    Jamf App Installers is Jamf's vendor-curated catalog of macOS app
    titles available for automated update management in Jamf Pro / Jamf
    School / Jamf Now. The catalog is published as an HTML table on
    learn.jamf.com (the documentation site) and contains three columns:

    - **Title Name** stored as ``title``, the primary key. Catalog
      titles are unique.
    - **Source** stored as ``source``, one of ``"Jamf"`` (Jamf hosts the
      installer) or ``"External"`` (Jamf metadata + a third-party host).
    - **Host Name** stored as ``host``, the download host for External
      sources or ``None`` when Jamf hosts. Upstream represents the
      Jamf-hosted case as the literal string ``"--"``; we normalize to
      ``None`` at ingest.

    **Coverage-indicator only**. The public HTML catalog does not expose
    bundle_id, version, download URL, or Jamf Software Title ID; just the
    three fields above. When Andrew gets access to a live Jamf Pro
    instance (the underlying unlisted API endpoint provides those richer
    fields), this model can grow additional columns and the stitch logic
    can be extended to populate them.
    """

    __tablename__ = "jamf_app_installers"

    title: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String)
    host: Mapped[str | None] = mapped_column(String, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
