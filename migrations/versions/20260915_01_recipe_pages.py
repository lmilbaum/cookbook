"""Store full standalone recipe pages.

Revision ID: 20260915_01
Revises: 20260914_01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260915_01"
down_revision = "20260914_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_pages",
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("html", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("slug"),
    )


def downgrade() -> None:
    op.drop_table("recipe_pages")
