"""Add recipe_made_dates table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260927_02"
down_revision = "20260927_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_made_dates",
        sa.Column("recipe_id", sa.Text(), nullable=False),
        sa.Column("made_on", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("recipe_id", "made_on"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_recipe_made_dates_made_on", "recipe_made_dates", ["made_on"])


def downgrade() -> None:
    op.drop_index("ix_recipe_made_dates_made_on", table_name="recipe_made_dates")
    op.drop_table("recipe_made_dates")
