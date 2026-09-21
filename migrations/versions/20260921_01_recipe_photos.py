"""Store recipe card photos in the database instead of *_posts_assets/ files.

Revision ID: 20260921_01
Revises: 20260919_03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260921_01"
down_revision = "20260919_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_photos",
        sa.Column("recipe_id", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("recipe_id"),
    )


def downgrade() -> None:
    op.drop_table("recipe_photos")
