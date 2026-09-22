"""add_reading_sessions

Revision ID: l9m0n1o2p3q4
Revises: k8l9m0n1o2p3
Create Date: 2026-09-21 22:20:00.000000

Adds ``reading_sessions`` — real tracked active reading time written by the
reader's progress-save tick. Stats/streaks/goals aggregate it; the old
per-reading-day heuristic stays as fallback for days with no sessions.

Also drops the orphaned ``reading_goals`` table (migration a1c2d3e4f5g6
created it, but no model/route/UI ever used it). The daily goal is a plain
settings key instead.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "l9m0n1o2p3q4"
down_revision: Union[str, Sequence[str], None] = "k8l9m0n1o2p3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create reading_sessions; drop the orphaned reading_goals table."""
    op.create_table(
        "reading_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "book_id",
            sa.Integer(),
            sa.ForeignKey("books.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("minutes", sa.Float(), nullable=False),
    )
    op.create_index("ix_reading_sessions_book_id", "reading_sessions", ["book_id"])
    op.create_index("ix_reading_sessions_started_at", "reading_sessions", ["started_at"])
    op.execute("DROP TABLE IF EXISTS reading_goals")


def downgrade() -> None:
    """Drop reading_sessions (reading_goals stays dropped — it was dead)."""
    op.drop_index("ix_reading_sessions_started_at", table_name="reading_sessions")
    op.drop_index("ix_reading_sessions_book_id", table_name="reading_sessions")
    op.drop_table("reading_sessions")
