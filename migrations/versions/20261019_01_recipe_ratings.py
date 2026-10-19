"""Add recipe_ratings table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261019_01"
down_revision = "20260928_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_ratings",
        sa.Column("recipe_id", sa.Text(), nullable=False),
        sa.Column("rating", sa.String(length=4), nullable=False),
        sa.PrimaryKeyConstraint("recipe_id"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.CheckConstraint("rating IN ('up','down')", name="ck_recipe_ratings_rating"),
    )


def downgrade() -> None:
    op.drop_table("recipe_ratings")
