"""initial schema

Revision ID: 6b9eb59e6fa6
Revises:
Create Date: 2026-05-02 13:27:08.229807

Rebuilt from the current model graph on 2026-06-29. The original revision body
only emitted ``create_index`` calls and never created any tables, so a fresh
``alembic upgrade head`` always failed; production databases were masked by the
old ``Base.metadata.create_all()`` + ``stamp(head)`` bootstrap in the app
lifespan. This file now creates the complete baseline schema. Existing
databases are already stamped at this revision id, so they will not re-run it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b9eb59e6fa6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the full baseline schema."""
    op.create_table('books',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('author', sa.String(length=300), nullable=True),
    sa.Column('path', sa.String(length=1000), nullable=False),
    sa.Column('cover_path', sa.String(length=1000), nullable=True),
    sa.Column('format', sa.String(length=20), nullable=False),
    sa.Column('total_chapters', sa.Integer(), nullable=False),
    sa.Column('current_chapter', sa.Integer(), nullable=False),
    sa.Column('progress', sa.Float(), nullable=False),
    sa.Column('is_favorite', sa.Boolean(), nullable=False),
    sa.Column('is_recent', sa.Boolean(), nullable=False),
    sa.Column('is_hidden', sa.Boolean(), nullable=False),
    sa.Column('file_size', sa.Integer(), nullable=False),
    sa.Column('added_date', sa.DateTime(), nullable=False),
    sa.Column('last_read_date', sa.DateTime(), nullable=True),
    sa.Column('publisher', sa.String(length=300), nullable=True),
    sa.Column('publish_date', sa.String(length=50), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('language', sa.String(length=20), nullable=True),
    sa.Column('isbn', sa.String(length=30), nullable=True),
    sa.Column('total_pages', sa.Integer(), nullable=False),
    sa.Column('storage_type', sa.String(length=10), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('path')
    )
    op.create_index(op.f('ix_books_added_date'), 'books', ['added_date'], unique=False)
    op.create_index(op.f('ix_books_author'), 'books', ['author'], unique=False)
    op.create_index('ix_books_format_hidden', 'books', ['format', 'is_hidden'], unique=False)
    op.create_index('ix_books_hidden_added', 'books', ['is_hidden', 'added_date'], unique=False)
    op.create_index('ix_books_hidden_favorite', 'books', ['is_hidden', 'is_favorite'], unique=False)
    op.create_index('ix_books_hidden_title', 'books', ['is_hidden', 'title'], unique=False)
    op.create_index(op.f('ix_books_is_favorite'), 'books', ['is_favorite'], unique=False)
    op.create_index(op.f('ix_books_is_hidden'), 'books', ['is_hidden'], unique=False)
    op.create_index(op.f('ix_books_is_recent'), 'books', ['is_recent'], unique=False)
    op.create_index(op.f('ix_books_last_read_date'), 'books', ['last_read_date'], unique=False)
    op.create_index(op.f('ix_books_progress'), 'books', ['progress'], unique=False)
    op.create_index('ix_books_recent_hidden', 'books', ['is_recent', 'is_hidden'], unique=False)
    op.create_index('ix_books_storage_type', 'books', ['storage_type'], unique=False)
    op.create_index(op.f('ix_books_title'), 'books', ['title'], unique=False)
    op.create_table('categories',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('reading_goals',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('goal_type', sa.String(length=10), nullable=False),
    sa.Column('target_minutes', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('settings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_settings_key'), 'settings', ['key'], unique=True)
    op.create_table('annotations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('chapter_index', sa.Integer(), nullable=False),
    sa.Column('start_position', sa.Integer(), nullable=False),
    sa.Column('end_position', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('color', sa.String(length=20), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_annotations_book_chapter', 'annotations', ['book_id', 'chapter_index'], unique=False)
    op.create_index(op.f('ix_annotations_book_id'), 'annotations', ['book_id'], unique=False)
    op.create_table('book_categories',
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('book_id', 'category_id')
    )
    op.create_index(op.f('ix_book_categories_book_id'), 'book_categories', ['book_id'], unique=False)
    op.create_index(op.f('ix_book_categories_category_id'), 'book_categories', ['category_id'], unique=False)
    op.create_index('ix_book_categories_composite', 'book_categories', ['category_id', 'book_id'], unique=False)
    op.create_table('book_summaries',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('summary_text', sa.Text(), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('book_id')
    )
    op.create_table('bookmarks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('chapter_index', sa.Integer(), nullable=False),
    sa.Column('position_in_chapter', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bookmarks_book_chapter', 'bookmarks', ['book_id', 'chapter_index'], unique=False)
    op.create_index(op.f('ix_bookmarks_book_id'), 'bookmarks', ['book_id'], unique=False)
    op.create_table('chapter_summaries',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('chapter_index', sa.Integer(), nullable=False),
    sa.Column('chapter_title', sa.String(length=500), nullable=True),
    sa.Column('summary_text', sa.Text(), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chapter_summaries_book_chapter', 'chapter_summaries', ['book_id', 'chapter_index'], unique=True)
    op.create_index(op.f('ix_chapter_summaries_book_id'), 'chapter_summaries', ['book_id'], unique=False)
    op.create_index(op.f('ix_chapter_summaries_provider'), 'chapter_summaries', ['provider'], unique=False)
    op.create_table('notes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('chapter_index', sa.Integer(), nullable=False),
    sa.Column('position_in_chapter', sa.Integer(), nullable=False),
    sa.Column('quoted_text', sa.Text(), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('color', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notes_book_chapter', 'notes', ['book_id', 'chapter_index'], unique=False)
    op.create_index(op.f('ix_notes_book_id'), 'notes', ['book_id'], unique=False)


def downgrade() -> None:
    """Drop the full baseline schema."""
    op.drop_index(op.f('ix_notes_book_id'), table_name='notes')
    op.drop_index('ix_notes_book_chapter', table_name='notes')
    op.drop_table('notes')
    op.drop_index(op.f('ix_chapter_summaries_provider'), table_name='chapter_summaries')
    op.drop_index(op.f('ix_chapter_summaries_book_id'), table_name='chapter_summaries')
    op.drop_index('ix_chapter_summaries_book_chapter', table_name='chapter_summaries')
    op.drop_table('chapter_summaries')
    op.drop_index(op.f('ix_bookmarks_book_id'), table_name='bookmarks')
    op.drop_index('ix_bookmarks_book_chapter', table_name='bookmarks')
    op.drop_table('bookmarks')
    op.drop_table('book_summaries')
    op.drop_index('ix_book_categories_composite', table_name='book_categories')
    op.drop_index(op.f('ix_book_categories_category_id'), table_name='book_categories')
    op.drop_index(op.f('ix_book_categories_book_id'), table_name='book_categories')
    op.drop_table('book_categories')
    op.drop_index(op.f('ix_annotations_book_id'), table_name='annotations')
    op.drop_index('ix_annotations_book_chapter', table_name='annotations')
    op.drop_table('annotations')
    op.drop_index(op.f('ix_settings_key'), table_name='settings')
    op.drop_table('settings')
    op.drop_table('reading_goals')
    op.drop_table('categories')
    op.drop_index(op.f('ix_books_title'), table_name='books')
    op.drop_index('ix_books_storage_type', table_name='books')
    op.drop_index('ix_books_recent_hidden', table_name='books')
    op.drop_index(op.f('ix_books_progress'), table_name='books')
    op.drop_index(op.f('ix_books_last_read_date'), table_name='books')
    op.drop_index(op.f('ix_books_is_recent'), table_name='books')
    op.drop_index(op.f('ix_books_is_hidden'), table_name='books')
    op.drop_index(op.f('ix_books_is_favorite'), table_name='books')
    op.drop_index('ix_books_hidden_title', table_name='books')
    op.drop_index('ix_books_hidden_favorite', table_name='books')
    op.drop_index('ix_books_hidden_added', table_name='books')
    op.drop_index('ix_books_format_hidden', table_name='books')
    op.drop_index(op.f('ix_books_author'), table_name='books')
    op.drop_index(op.f('ix_books_added_date'), table_name='books')
    op.drop_table('books')
