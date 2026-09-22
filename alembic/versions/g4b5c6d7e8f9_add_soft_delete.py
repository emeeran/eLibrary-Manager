"""add_soft_delete

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-06-30 14:00:00.000000

Adds ``books.is_deleted`` for soft-deleting volumes that vanish from a linked
Calibre library (spec 011 v1.2 prune). Soft-deleted books are excluded from the
normal list/count views but remain recoverable (restore clears the flag). The
existing "Deleted" sidebar (stale-file detection) is unaffected.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the is_deleted soft-delete column."""
    with op.batch_alter_table("books") as batch_op:
        batch_op.add_column(
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.create_index("ix_books_is_deleted", "books", ["is_deleted"])


def downgrade() -> None:
    """Drop the is_deleted column."""
    op.drop_index("ix_books_is_deleted", table_name="books")
    with op.batch_alter_table("books") as batch_op:
        batch_op.drop_column("is_deleted")
