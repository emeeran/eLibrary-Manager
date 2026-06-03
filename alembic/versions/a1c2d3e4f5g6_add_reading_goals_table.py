"""add reading_goals table

Revision ID: a1c2d3e4f5g6
Revises: 6b9eb59e6fa6
Create Date: 2026-06-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c2d3e4f5g6'
down_revision: Union[str, None] = '6b9eb59e6fa6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use IF NOT EXISTS since init_db() may have already created the table
    op.create_table(
        'reading_goals',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('goal_type', sa.String(length=10), nullable=False, server_default='daily'),
        sa.Column('target_minutes', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table('reading_goals')
