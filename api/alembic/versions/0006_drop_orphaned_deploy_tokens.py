"""drop the orphaned deploy_tokens table on pre-Alembic databases

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-14 12:00:00.000000

``deploy_tokens`` is a leftover table from removed functionality; it predates
Alembic, so the production DB still carries it while the models and the chain
do not. Nothing reads or writes it. Drop it where it exists; on databases built
by the chain (fresh, test, dev) it was never created, so this is a no-op.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    """True if ``table`` currently exists (guards the conditional drop)."""
    return table in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    if _has_table("deploy_tokens"):
        op.drop_table("deploy_tokens")


def downgrade() -> None:
    """Downgrade schema."""
    # The orphan table isn't modeled, so there's nothing to faithfully recreate.
    pass
