"""add_calibre_sync_and_series

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-30 12:00:00.000000

Adds columns that support incremental Calibre re-sync (spec 011 v1.1):

* ``calibre_last_modified`` — the raw Calibre ``books.last_modified`` timestamp
  string, used to detect whether a previously-imported volume has changed
  metadata since the last sync (exact string equality; no date parsing across
  Calibre versions).
* ``series`` / ``series_index`` — Calibre series membership, captured at import
  so series can drive sorting, grouping, and faceted search.

All nullable; existing books remain untouched.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add incremental-sync + series columns."""
    with op.batch_alter_table("books") as batch_op:
        batch_op.add_column(
            sa.Column("calibre_last_modified", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("series", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("series_index", sa.Float(), nullable=True))
    # Series lookups/grouping are common; index it.
    op.create_index("ix_books_series", "books", ["series"])


def downgrade() -> None:
    """Drop incremental-sync + series columns."""
    op.drop_index("ix_books_series", table_name="books")
    with op.batch_alter_table("books") as batch_op:
        batch_op.drop_column("series_index")
        batch_op.drop_column("series")
        batch_op.drop_column("calibre_last_modified")
