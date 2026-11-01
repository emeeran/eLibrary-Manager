"""add_opds_catalogs

Revision ID: m0n1o2p3q4r5
Revises: l9m0n1o2p3q4
Create Date: 2026-11-01 01:30:00.000000

Adds ``opds_catalogs`` — registered OPDS network catalogs (spec 015,
Moon+ Reader "Net Library" parity). Credentials are stored Fernet-encrypted
(``password_encrypted``), mirroring NAS settings secret handling.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m0n1o2p3q4r5"
down_revision: Union[str, Sequence[str], None] = "l9m0n1o2p3q4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the opds_catalogs table."""
    op.create_table(
        "opds_catalogs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("username", sa.String(length=200), nullable=True),
        sa.Column("password_encrypted", sa.String(length=1000), nullable=True),
        sa.Column("added_date", sa.DateTime(), nullable=True),
        sa.Column("last_browsed", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_opds_catalogs_name", "opds_catalogs", ["name"])


def downgrade() -> None:
    """Drop the opds_catalogs table."""
    op.drop_index("ix_opds_catalogs_name", table_name="opds_catalogs")
    op.drop_table("opds_catalogs")
