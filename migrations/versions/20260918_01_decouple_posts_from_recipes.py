"""Let a post outlive its recipe, so a rejected import doesn't get re-fetched.

A post rejected as "not a recipe" now has its recipe row deleted outright
instead of merely hidden -- but the post row (and its is_recipe = false
marker) stays, since the importer's dedup relies on every seen shortcode
having a posts row. That means posts.shortcode can no longer require a
matching recipes.id, so the foreign key is dropped.

Revision ID: 20260918_01
Revises: 20260917_03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260918_01"
down_revision = "20260917_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the posts->recipes foreign key and delete already-hidden recipes."""

    with op.batch_alter_table("posts") as batch_op:
        batch_op.drop_constraint("fk_posts_shortcode_recipes", type_="foreignkey")
    op.execute(
        "DELETE FROM recipes WHERE id IN (SELECT shortcode FROM posts WHERE is_recipe = false)"
    )


def downgrade() -> None:
    """Restore the foreign key.

    Any post left without a matching recipe (because it was rejected under
    the new behavior) gets a blank recipe row recreated so the constraint
    can be re-added.
    """

    connection = op.get_bind()
    orphaned_shortcodes = connection.execute(
        sa.text(
            "SELECT shortcode FROM posts WHERE shortcode NOT IN (SELECT id FROM recipes)"
        )
    ).scalars().all()
    for shortcode in orphaned_shortcodes:
        connection.execute(
            sa.text(
                "INSERT INTO recipes (id, image_url, caption, timestamp_utc, title,"
                " recipe_url, recipe_name, source)"
                " VALUES (:id, '', '', '', '', '', '', 'lizapanelim')"
            ),
            {"id": shortcode},
        )
    with op.batch_alter_table("posts") as batch_op:
        batch_op.create_foreign_key("fk_posts_shortcode_recipes", "recipes", ["shortcode"], ["id"])
