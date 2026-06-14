"""drop the orphaned apps.cves column on pre-Alembic databases

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-13 17:00:00.000000

``cves`` was removed from the model long ago (commit 1f2ac0a) but no migration
ever dropped it, and the production DB predates Alembic, so it was stamped at
baseline while still carrying the column. The current stitch never writes
``cves``, so its ``NOT NULL`` constraint fails every ``apps`` upsert and freezes
the catalog. Drop it where it still exists; on databases built by the chain
(fresh, test, dev) the column was never created, so this is a no-op.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    """True if ``table`` currently has ``column`` (guards the conditional drop)."""
    inspector = sa.inspect(op.get_bind())
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    """Upgrade schema."""
    if _has_column("apps", "cves"):
        with op.batch_alter_table("apps", schema=None) as batch_op:
            batch_op.drop_column("cves")


def downgrade() -> None:
    """Downgrade schema."""
    if not _has_column("apps", "cves"):
        with op.batch_alter_table("apps", schema=None) as batch_op:
            batch_op.add_column(sa.Column("cves", sa.JSON(), nullable=True))
