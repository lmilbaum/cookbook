"""Allow posts to be retained without being displayed as recipes.

Revision ID: 20260910_02
Revises: 20260910_01
Create Date: 2026-09-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260910_02"
down_revision = "20260910_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Default existing and new posts to recipe visibility."""

    op.add_column(
        "posts",
        sa.Column("is_recipe", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.alter_column("posts", "is_recipe", server_default=None)


def downgrade() -> None:
    """Remove the recipe visibility marker."""

    op.drop_column("posts", "is_recipe")
