"""Use only instagram and manual for recipe added_via values."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260928_01"
down_revision = "20260927_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_constraint("ck_recipes_added_via", type_="check")
    op.execute(
        sa.text(
            "UPDATE recipes SET added_via = 'manual' "
            "WHERE added_via IN ('website', 'custom')"
        )
    )
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.create_check_constraint(
            "ck_recipes_added_via", "added_via IN ('instagram','manual')"
        )


def downgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_constraint("ck_recipes_added_via", type_="check")
    op.execute(
        sa.text(
            "UPDATE recipes SET added_via = CASE "
            "WHEN id LIKE 'custom-%' THEN 'custom' ELSE 'website' END "
            "WHERE added_via = 'manual'"
        )
    )
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.create_check_constraint(
            "ck_recipes_added_via", "added_via IN ('instagram','website','custom')"
        )
