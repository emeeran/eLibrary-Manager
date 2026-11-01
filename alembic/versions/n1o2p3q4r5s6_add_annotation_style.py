"""add_annotation_style

Revision ID: n1o2p3q4r5s6
Revises: m0n1o2p3q4r5
Create Date: 2026-11-01 03:00:00.000000

Adds ``annotations.style`` — visual style of a highlight (spec 005 v1.2,
Moon+ parity): highlight (default, existing behavior) | underline |
squiggly | strikethrough.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n1o2p3q4r5s6"
down_revision: Union[str, Sequence[str], None] = "m0n1o2p3q4r5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the style column with a 'highlight' backfill."""
    op.add_column(
        "annotations",
        sa.Column("style", sa.String(length=20), nullable=False, server_default="highlight"),
    )


def downgrade() -> None:
    """Drop the style column."""
    op.drop_column("annotations", "style")
