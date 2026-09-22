"""add_content_search

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-30 13:00:00.000000

Adds full-text search over book CONTENT (spec 012):

* ``book_contents`` — a lightweight per-book extraction-status tracker
  (``book_id``, ``extract_status``, ``char_count``, ``source_mtime``,
  ``extracted_at``). It does NOT store the text — the text lives in the FTS table.
* ``books_content_fts`` — a content-bearing FTS5 virtual table
  (``book_id UNINDEXED`` + tokenized ``content``) populated by the background
  content-backfill job. Synced at the application layer (not triggers) because
  extraction is deferred/async and runs in a background task.

All existing books are seeded as ``extract_status='pending'`` so the first
backfill run picks them up. The FTS table creation is guarded so a SQLite build
without fts5 is skipped (the repository then falls back to ilike search).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the content-status table, seed it, and create the content FTS5 index."""
    bind = op.get_bind()

    exists = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='book_contents'")
    ).scalar()
    if not exists:
        op.create_table(
            "book_contents",
            sa.Column(
                "book_id",
                sa.Integer(),
                sa.ForeignKey("books.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("extract_status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source_mtime", sa.Float(), nullable=True),
            sa.Column("extracted_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_book_contents_status", "book_contents", ["extract_status"])

    # Seed pending rows for any book not yet tracked (idempotent across re-runs).
    op.execute(
        "INSERT INTO book_contents(book_id, extract_status) "
        "SELECT b.id, 'pending' FROM books b "
        "LEFT JOIN book_contents bc ON bc.book_id = b.id "
        "WHERE bc.book_id IS NULL"
    )

    fts_exists = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='books_content_fts'")
    ).scalar()
    if fts_exists:
        return
    try:
        op.execute(
            "CREATE VIRTUAL TABLE books_content_fts USING fts5("
            "book_id UNINDEXED, content, tokenize='unicode61')"
        )
    except Exception:
        # fts5 not compiled in — skip; repository falls back to ilike search.
        return


def downgrade() -> None:
    """Drop the content FTS5 index and the content-status table."""
    op.execute("DROP TABLE IF EXISTS books_content_fts")
    op.drop_index("ix_book_contents_status", table_name="book_contents")
    op.drop_table("book_contents")
