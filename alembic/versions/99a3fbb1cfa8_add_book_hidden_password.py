"""add_book_hidden_password

Revision ID: 99a3fbb1cfa8
Revises: a1c2d3e4f5g6
Create Date: 2026-06-29 15:32:38.633339

Adds ``books.hidden_password`` (nullable) for per-book Fernet-encrypted
passwords (approach A: each hidden book has its own password).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "99a3fbb1cfa8"
down_revision: Union[str, Sequence[str], None] = "a1c2d3e4f5g6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the per-book hidden_password column and normalize any legacy values."""
    op.add_column(
        "books",
        sa.Column("hidden_password", sa.String(length=1000), nullable=True),
    )
    # The column previously held Fernet (reversible) ciphertext in an earlier
    # iteration of this feature. bcrypt hashes start with "$2"; any other value
    # is legacy/unverifiable, so clear it and unhide the book to avoid leaving
    # books locked behind passwords we deliberately no longer store that way.
    op.execute(
        "UPDATE books SET hidden_password = NULL, is_hidden = 0 "
        "WHERE hidden_password IS NOT NULL AND hidden_password NOT LIKE '$2%'"
    )


def downgrade() -> None:
    """Drop the per-book hidden_password column."""
    op.drop_column("books", "hidden_password")
