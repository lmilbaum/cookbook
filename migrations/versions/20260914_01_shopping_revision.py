"""Track shopping-list revisions without changing existing items."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260914_01"
down_revision = "20260913_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shopping_list_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.execute("INSERT INTO shopping_list_state (id, revision) SELECT 1, 1 WHERE EXISTS (SELECT 1 FROM ingredients)")


def downgrade() -> None:
    op.drop_table("shopping_list_state")
