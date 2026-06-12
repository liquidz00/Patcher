"""drop the always-null apps.latest_release_date column

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('apps', schema=None) as batch_op:
        batch_op.drop_column('latest_release_date')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('apps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('latest_release_date', sa.Date(), nullable=True))
