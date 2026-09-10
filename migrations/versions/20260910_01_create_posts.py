"""Create the recipe post table.

Revision ID: 20260910_01
Revises: 20260908_01
Create Date: 2026-09-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260910_01"
down_revision = "20260908_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create storage for imported Instagram recipe posts."""

    op.create_table(
        "posts",
        sa.Column("shortcode", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("timestamp_utc", sa.String(length=64), nullable=False),
        sa.Column("likes", sa.Integer(), nullable=False),
        sa.Column("comments", sa.Integer(), nullable=False),
        sa.Column("typename", sa.String(length=128), nullable=False),
        sa.Column("is_video", sa.Boolean(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("recipe_url", sa.Text(), nullable=False),
        sa.Column("recipe_urls", sa.JSON(), nullable=False),
        sa.Column("recipe_names", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("shortcode"),
    )
    op.create_index("ix_posts_timestamp_utc", "posts", ["timestamp_utc"])


def downgrade() -> None:
    """Remove the recipe post table."""

    op.drop_index("ix_posts_timestamp_utc", table_name="posts")
    op.drop_table("posts")
