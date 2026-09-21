"""add_reading_status

Revision ID: k8l9m0n1o2p3
Revises: j7k8l9m0n1o2
Create Date: 2026-09-21 20:40:00.000000

Adds ``books.reading_status`` (none|to_read|reading|finished) for triage
shelves. Backfilled once from reading progress: >=95% → finished (matches the
stats "completed" definition), >0 → reading, else none. Indexed: shelf
filters hit it on every list query.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k8l9m0n1o2p3"
down_revision: Union[str, Sequence[str], None] = "j7k8l9m0n1o2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add reading_status, backfill from progress, index it."""
    with op.batch_alter_table("books") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reading_status", sa.String(10), nullable=False, server_default="none"
            )
        )
    op.execute(
        """
        UPDATE books SET reading_status = 'finished' WHERE progress >= 95
        """
    )
    op.execute(
        """
        UPDATE books SET reading_status = 'reading'
        WHERE progress > 0 AND progress < 95
        """
    )
    op.create_index("ix_books_reading_status", "books", ["reading_status"])


def downgrade() -> None:
    """Drop the reading_status column."""
    op.drop_index("ix_books_reading_status", table_name="books")
    with op.batch_alter_table("books") as batch_op:
        batch_op.drop_column("reading_status")
