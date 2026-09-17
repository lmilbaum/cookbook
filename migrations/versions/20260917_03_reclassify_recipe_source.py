"""Reclassify recipe source: an Instagram post always counts as hers.

A recipe she posted to Instagram is hers even when the recipe itself links
out to someone else's site (e.g. a repost of a find) -- the recipe link's
domain should only decide the source when there was no Instagram post at
all.

Revision ID: 20260917_03
Revises: 20260917_02
"""
from __future__ import annotations

from urllib.parse import urlsplit

from alembic import op
import sqlalchemy as sa


revision = "20260917_03"
down_revision = "20260917_02"
branch_labels = None
depends_on = None

_LIZAPANELIM_HOST = "lizapanelim.com"


def _is_lizapanelim_url(url: str) -> bool:
    netloc = urlsplit(url).netloc.lower()
    return not netloc or netloc.removeprefix("www.") == _LIZAPANELIM_HOST


def _classify(recipe_url: str, has_post: bool) -> str:
    if has_post:
        return "lizapanelim"
    url = recipe_url.strip()
    if not url or _is_lizapanelim_url(url):
        return "lizapanelim"
    return "other"


def upgrade() -> None:
    """Recompute every recipe's source with Instagram origin taking precedence."""

    connection = op.get_bind()
    posted_shortcodes = {row[0] for row in connection.execute(sa.text("SELECT shortcode FROM posts"))}
    rows = connection.execute(sa.text("SELECT id, recipe_url, source FROM recipes")).fetchall()
    for recipe_id, recipe_url, current_source in rows:
        correct_source = _classify(recipe_url or "", recipe_id in posted_shortcodes)
        if correct_source != current_source:
            connection.execute(
                sa.text("UPDATE recipes SET source = :source WHERE id = :id"),
                {"source": correct_source, "id": recipe_id},
            )


def downgrade() -> None:
    """Source classification is derived data; nothing to structurally reverse."""
