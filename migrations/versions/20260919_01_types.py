"""Create the recipe types table.

Revision ID: 20260919_01
Revises: 20260918_01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260919_01"
down_revision = "20260918_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add an empty table; existing recipe state is left untouched."""

    op.create_table(
        "types",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
    )


def downgrade() -> None:
    op.drop_table("types")
