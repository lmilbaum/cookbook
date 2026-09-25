"""Add source_name column to recipes for Instagram display name.

Revision ID: 20260925_01
Revises: 20260921_01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260925_01"
down_revision = "20260921_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(sa.Column("source_name", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_column("source_name")
