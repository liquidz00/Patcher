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

    The HTML catalog only ever populates ``title``/``source``/``host``. The
    remaining columns come from Jamf Pro's App Installers *titles* API (see
    :func:`patcher_api.ingest.jamf_app_installers.fetch_jai_catalog`), which is
    catalog-global, so no specific tenant is required. They're nullable because
    an HTML-only row predates the API enrichment.

    - ``bundle_id`` — the canonical bundle identifier; the exact stitch key,
      used as a precision overlay over name matching and backfilled onto
      matched apps that lack one.
    - ``version`` — the catalog's current version for the title.
    - ``jamf_id`` — Jamf's stable title identifier (e.g. ``"001"``), a durable
      cross-reference for hard-to-match titles.
    - ``download_url`` — the title's installer source URL.
    - ``architecture`` — ``universal`` / ``arm64`` / ``x86_64``.
    """

    __tablename__ = "jamf_app_installers"

    title: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String)
    host: Mapped[str | None] = mapped_column(String, nullable=True)
    bundle_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    jamf_id: Mapped[str | None] = mapped_column(String, nullable=True)
    download_url: Mapped[str | None] = mapped_column(String, nullable=True)
    architecture: Mapped[str | None] = mapped_column(String, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
