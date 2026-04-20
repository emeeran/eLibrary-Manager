"""add composite indexes

Revision ID: 670d14a2b775
Revises: ec5edc8d84b7
Create Date: 2026-04-20 18:37:09.031521

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '670d14a2b775'
down_revision: Union[str, Sequence[str], None] = 'ec5edc8d84b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_annotations_book_chapter', 'annotations', ['book_id', 'chapter_index'], unique=False)
    op.create_index('ix_bookmarks_book_chapter', 'bookmarks', ['book_id', 'chapter_index'], unique=False)
    op.create_index('ix_chapter_summaries_book_chapter', 'chapter_summaries', ['book_id', 'chapter_index'], unique=True)
    op.create_index('ix_notes_book_chapter', 'notes', ['book_id', 'chapter_index'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_notes_book_chapter', table_name='notes')
    op.drop_index('ix_chapter_summaries_book_chapter', table_name='chapter_summaries')
    op.drop_index('ix_bookmarks_book_chapter', table_name='bookmarks')
    op.drop_index('ix_annotations_book_chapter', table_name='annotations')
