"""Store recipe page images.

Revision ID: 20260915_02
Revises: 20260915_01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260915_02"
down_revision = "20260915_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_images",
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("filename"),
    )


def downgrade() -> None:
    op.drop_table("recipe_images")
