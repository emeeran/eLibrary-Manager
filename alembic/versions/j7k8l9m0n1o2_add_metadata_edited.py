"""add_metadata_edited

Revision ID: j7k8l9m0n1o2
Revises: i6j7k8l9m0n1
Create Date: 2026-09-21 20:10:00.000000

Adds ``books.metadata_edited`` — set when the user hand-edits metadata fields
in eLM. The Calibre re-sync skips the metadata block for edited books so hand
edits are never clobbered (whole-book granularity, one flag).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j7k8l9m0n1o2"
down_revision: Union[str, Sequence[str], None] = "i6j7k8l9m0n1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the metadata_edited flag."""
    with op.batch_alter_table("books") as batch_op:
        batch_op.add_column(
            sa.Column("metadata_edited", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Drop the metadata_edited flag."""
    with op.batch_alter_table("books") as batch_op:
        batch_op.drop_column("metadata_edited")
