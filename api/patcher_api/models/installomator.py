from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from patcher_api.db import Base


class InstallomatorLabel(Base):
    """
    A single Installomator label, parsed from its ``.sh`` fragment.

    The label's ``packageID`` variable is the canonical bundle identifier
    Installomator authors declare — this is what makes Installomator the
    bundle_id authority for the join logic that links Cask records (which
    don't expose bundle_id) to ``apps`` rows.

    Common variables (``name``, ``type``, ``packageID``, ``downloadURL``,
    ``expectedTeamID``, ``appNewVersion``) are exposed as real columns;
    the full parsed payload is preserved in ``raw`` so consumers can see
    every variable the label declares — including shell expressions like
    ``downloadURL=$(curl -fs ...)`` stored verbatim.

    ``blob_sha`` is git's content-addressed SHA of the upstream ``.sh``
    fragment this row was parsed from. Ingest uses it to skip re-fetching
    labels whose content hasn't changed since the last run; an existing
    row whose ``blob_sha`` differs from upstream signals a content change
    that warrants re-parsing. Nullable so rows that pre-date the gating
    introduction re-fetch on the next ingest pass.
    """

    __tablename__ = "installomator_labels"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    install_type: Mapped[str | None] = mapped_column(String, nullable=True)
    package_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    download_url: Mapped[str | None] = mapped_column(String, nullable=True)
    expected_team_id: Mapped[str | None] = mapped_column(String, nullable=True)
    app_new_version: Mapped[str | None] = mapped_column(String, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON)
    blob_sha: Mapped[str | None] = mapped_column(String, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
