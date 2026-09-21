"""add_review

Revision ID: i6j7k8l9m0n1
Revises: h5i6j7k8l9m0
Create Date: 2026-09-21 19:50:00.000000

Adds ``books.review`` — the reader's own free-text review, the natural
companion to the existing 0-5 star rating. Nullable; never auto-populated
(unlike description, which may come from Calibre metadata).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i6j7k8l9m0n1"
down_revision: Union[str, Sequence[str], None] = "h5i6j7k8l9m0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the review column."""
    with op.batch_alter_table("books") as batch_op:
        batch_op.add_column(sa.Column("review", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop the review column."""
    with op.batch_alter_table("books") as batch_op:
        batch_op.drop_column("review")
