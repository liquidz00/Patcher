from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from patcher_api.db import Base


class Token(Base):
    """
    Bearer token issued to an authorized API consumer.

    Plaintext tokens are never stored — only their SHA-256 hash. The plaintext
    is shown once at grant time (via :mod:`scripts.grant_token`) and must be
    re-issued if lost.
    """

    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
