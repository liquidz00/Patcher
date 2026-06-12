"""drop the Mac App Store (MAS) source

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-12 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('app_source_details', schema=None) as batch_op:
        batch_op.drop_column('mas')
    op.drop_table('mas_apps')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        'mas_apps',
        sa.Column('bundle_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=True),
        sa.Column('release_date', sa.Date(), nullable=True),
        sa.Column('release_notes', sa.String(), nullable=True),
        sa.Column('store_url', sa.String(), nullable=True),
        sa.Column('minimum_os_version', sa.String(), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('raw', sa.JSON(), nullable=False),
        sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('bundle_id'),
    )
    with op.batch_alter_table('app_source_details', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mas', sa.JSON(), nullable=True))
