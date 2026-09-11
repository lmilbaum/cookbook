"""Create storage for the shared shopping list.

Revision ID: 20260911_01
Revises: 20260910_02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260911_01"
down_revision = "20260910_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add empty storage without changing existing file-backed lists."""

    op.create_table(
        "ingredients",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
    )
    op.create_table(
        "shopping_list",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("ingredient_id", sa.Integer(), sa.ForeignKey("ingredients.id"), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=True),
        sa.Column("done", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    """Remove shopping items before their referenced ingredients."""

    op.drop_table("shopping_list")
    op.drop_table("ingredients")
