"""Persist user-authored recipe state.

Revision ID: 20260913_01
Revises: 20260911_01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260913_01"
down_revision = "20260911_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("recipe_state")
