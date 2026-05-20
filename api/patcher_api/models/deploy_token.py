from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from patcher_api.db import Base

# Default lifetime applied when minting a new deploy token. 90 days balances
# rotation hygiene with operational friction for the CI workflow that
# consumes the token.
DEFAULT_LIFETIME = timedelta(days=90)


class DeployToken(Base):
    """
    Bearer token authorizing privileged catalog-deployment operations.

    Stored separately from the user-facing :class:`~patcher_api.models.token.Token`
    on purpose: user tokens only grant read access to ``/apps``-style routes;
    deploy tokens additionally grant the catalog-upload endpoint that swaps
    out the live DB. Keeping the tables distinct means revoking one class
    of credential doesn't accidentally affect the other, and an attacker
    who compromises a user token cannot pivot to a deploy operation.

    Same plaintext-never-stored hygiene as :class:`Token`: SHA-256 hash on
    insert, plaintext shown once via :mod:`scripts.grant_deploy_token` and
    re-issued if lost. Tokens carry an ``expires_at`` (default 90 days from
    creation) so a leaked token cannot live forever even if it's never
    rotated; ``expires_at = NULL`` is treated as "never expires" for
    backward compatibility with rows minted before this column existed.
    """

    __tablename__ = "deploy_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
