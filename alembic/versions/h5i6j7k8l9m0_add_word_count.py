"""add_word_count

Revision ID: h5i6j7k8l9m0
Revises: g4b5c6d7e8f9
Create Date: 2026-09-21 19:30:00.000000

Adds ``books.word_count`` — an approximate word count (chars/6) derived from
already-extracted body text, powering "time to read" estimates. Backfilled
once from ``book_contents.char_count`` for extracted books; subsequently
maintained by the extraction upsert. Nullable so non-extracted books carry no
estimate rather than a fake one.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h5i6j7k8l9m0"
down_revision: Union[str, Sequence[str], None] = "g4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add word_count and backfill it from extracted content."""
    with op.batch_alter_table("books") as batch_op:
        batch_op.add_column(sa.Column("word_count", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE books
        SET word_count = (SELECT bc.char_count / 6
                          FROM book_contents bc
                          WHERE bc.book_id = books.id
                            AND bc.extract_status = 'extracted')
        WHERE EXISTS (
            SELECT 1 FROM book_contents bc
            WHERE bc.book_id = books.id AND bc.extract_status = 'extracted'
        )
        """
    )


def downgrade() -> None:
    """Drop the word_count column."""
    with op.batch_alter_table("books") as batch_op:
        batch_op.drop_column("word_count")
