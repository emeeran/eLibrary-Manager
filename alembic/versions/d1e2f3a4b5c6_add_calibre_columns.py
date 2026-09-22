"""add_calibre_columns

Revision ID: d1e2f3a4b5c6
Revises: c4f1a2b3c4d5
Create Date: 2026-06-30 11:00:00.000000

Adds ``calibre_id`` and ``calibre_uuid`` columns to ``books`` so volumes
imported from a Calibre library can be linked back to their Calibre record
(for Calibre-Web deep-linking and re-sync detection). Both nullable; existing
books remain untouched.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c4f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Calibre linkage columns."""
    with op.batch_alter_table("books") as batch_op:
        batch_op.add_column(
            sa.Column("calibre_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("calibre_uuid", sa.String(length=64), nullable=True)
        )
    # Look up imported Calibre volumes by their Calibre book id quickly.
    op.create_index("ix_books_calibre_id", "books", ["calibre_id"])


def downgrade() -> None:
    """Drop Calibre linkage columns."""
    op.drop_index("ix_books_calibre_id", table_name="books")
    with op.batch_altering_table("books") as batch_op:
        batch_op.drop_column("calibre_uuid")
        batch_op.drop_column("calibre_id")
