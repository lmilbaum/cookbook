"""Establish the Alembic migration baseline.

Revision ID: 20260908_01
Revises:
Create Date: 2026-09-08
"""

from __future__ import annotations


revision = "20260908_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Record the migration baseline; application tables come next."""


def downgrade() -> None:
    """The baseline contains no application schema."""
