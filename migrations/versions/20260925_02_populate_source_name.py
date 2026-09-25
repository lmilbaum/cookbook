"""Populate source_name for recipes whose source handle is already known.

Revision ID: 20260925_02
Revises: 20260925_01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260925_02"
down_revision = "20260925_01"
branch_labels = None
depends_on = None

_KNOWN_NAMES: dict[str, str] = {
    "lizapanelim": "לייזה פאנלים",
}


def upgrade() -> None:
    conn = op.get_bind()
    for handle, display_name in _KNOWN_NAMES.items():
        conn.execute(
            sa.text(
                "UPDATE recipes SET source_name = :name"
                " WHERE source = :handle AND source_name = ''"
            ),
            {"name": display_name, "handle": handle},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for handle in _KNOWN_NAMES:
        conn.execute(
            sa.text(
                "UPDATE recipes SET source_name = ''"
                " WHERE source = :handle"
            ),
            {"handle": handle},
        )
