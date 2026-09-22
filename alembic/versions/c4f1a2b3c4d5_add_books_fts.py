"""add_books_fts

Revision ID: c4f1a2b3c4d5
Revises: 99a3fbb1cfa8
Create Date: 2026-06-29 16:00:00.000000

Adds an FTS5 full-text index over books (title, author) for fast prefix-token
search at scale, replacing the O(n) ``LIKE '%term%'`` scan for the library
search box. External-content table backed by ``books`` with sync triggers.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "99a3fbb1cfa8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the FTS5 index, backfill it, and install sync triggers.

    All statements are idempotent (``IF NOT EXISTS`` / guarded) so the revision
    is safe to re-run if a partial application occurred. If the SQLite build
    lacks the fts5 extension the CREATE raises and we bail out (the repository
    then falls back to ilike search).
    """
    bind = op.get_bind()
    # Skip if already created (idempotent re-run).
    existing = bind.execute(
        __import__("sqlalchemy").text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='books_fts'"
        )
    ).scalar()
    if existing:
        return

    try:
        op.execute(
            "CREATE VIRTUAL TABLE books_fts USING fts5("
            "title, author, content='books', content_rowid='id')"
        )
    except Exception:
        # fts5 not compiled in — skip; repository falls back to ilike.
        return

    op.execute(
        "INSERT INTO books_fts(rowid, title, author) "
        "SELECT id, title, COALESCE(author, '') FROM books"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS books_fts_ai AFTER INSERT ON books BEGIN "
        "INSERT INTO books_fts(rowid, title, author) "
        "VALUES (new.id, new.title, COALESCE(new.author, '')); END"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS books_fts_ad AFTER DELETE ON books BEGIN "
        "INSERT INTO books_fts(books_fts, rowid, title, author) "
        "VALUES('delete', old.id, old.title, COALESCE(old.author, '')); END"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS books_fts_au AFTER UPDATE OF title, author ON books BEGIN "
        "INSERT INTO books_fts(books_fts, rowid, title, author) "
        "VALUES('delete', old.id, old.title, COALESCE(old.author, '')); "
        "INSERT INTO books_fts(rowid, title, author) "
        "VALUES (new.id, new.title, COALESCE(new.author, '')); END"
    )


def downgrade() -> None:
    """Drop triggers and the FTS5 index."""
    op.execute("DROP TRIGGER IF EXISTS books_fts_au")
    op.execute("DROP TRIGGER IF EXISTS books_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS books_fts_ai")
    op.execute("DROP TABLE IF EXISTS books_fts")
