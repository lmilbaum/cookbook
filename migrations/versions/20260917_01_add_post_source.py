"""Track each post's recipe source (lizapanelim.com vs. other sites).

Revision ID: 20260917_01
Revises: 20260915_02
"""
from __future__ import annotations

from urllib.parse import urlsplit

import sqlalchemy as sa
from alembic import op

revision = "20260917_01"
down_revision = "20260915_02"
branch_labels = None
depends_on = None

_LIZAPANELIM_HOST = "lizapanelim.com"


def _is_lizapanelim_url(url: str) -> bool:
    """A recipe link counts as hers if it has no host (a local page) or is on her domain."""

    netloc = urlsplit(url).netloc.lower()
    return not netloc or netloc.removeprefix("www.") == _LIZAPANELIM_HOST


def _classify_source(recipe_url: str, recipe_urls: list[str]) -> str:
    """Classify a post by whether all of its recipe links point to lizapanelim.com."""

    urls = [url.strip() for url in [recipe_url, *recipe_urls] if url.strip()]
    if not urls or all(_is_lizapanelim_url(url) for url in urls):
        return "lizapanelim"
    return "other"


def upgrade() -> None:
    """Add the source column and backfill it from each post's existing recipe links."""

    op.add_column(
        "posts",
        sa.Column("source", sa.String(length=32), server_default="lizapanelim", nullable=False),
    )
    op.alter_column("posts", "source", server_default=None)

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT shortcode, recipe_url, recipe_urls FROM posts")).fetchall()
    for shortcode, recipe_url, recipe_urls in rows:
        source = _classify_source(recipe_url or "", list(recipe_urls or []))
        if source != "lizapanelim":
            connection.execute(
                sa.text("UPDATE posts SET source = :source WHERE shortcode = :shortcode"),
                {"source": source, "shortcode": shortcode},
            )


def downgrade() -> None:
    """Remove the source column."""

    op.drop_column("posts", "source")
