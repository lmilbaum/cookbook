"""Split posts into recipes (the primary entity) and posts (an optional Instagram attachment).

Revision ID: 20260917_02
Revises: 20260917_01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260917_02"
down_revision = "20260917_01"
branch_labels = None
depends_on = None

_OLD_POSTS = sa.table(
    "posts",
    sa.column("shortcode", sa.Text()),
    sa.column("url", sa.Text()),
    sa.column("image_url", sa.Text()),
    sa.column("caption", sa.Text()),
    sa.column("timestamp_utc", sa.String(length=64)),
    sa.column("likes", sa.Integer()),
    sa.column("comments", sa.Integer()),
    sa.column("typename", sa.String(length=128)),
    sa.column("is_video", sa.Boolean()),
    sa.column("title", sa.Text()),
    sa.column("recipe_url", sa.Text()),
    sa.column("recipe_urls", sa.JSON()),
    sa.column("recipe_names", sa.JSON()),
    sa.column("is_recipe", sa.Boolean()),
    sa.column("source", sa.String(length=32)),
)

_RECIPES = sa.table(
    "recipes",
    sa.column("id", sa.Text()),
    sa.column("image_url", sa.Text()),
    sa.column("caption", sa.Text()),
    sa.column("timestamp_utc", sa.String(length=64)),
    sa.column("title", sa.Text()),
    sa.column("recipe_url", sa.Text()),
    sa.column("recipe_name", sa.Text()),
    sa.column("source", sa.String(length=32)),
)

_NEW_POSTS = sa.table(
    "posts",
    sa.column("shortcode", sa.Text()),
    sa.column("url", sa.Text()),
    sa.column("typename", sa.String(length=128)),
    sa.column("is_video", sa.Boolean()),
    sa.column("is_recipe", sa.Boolean()),
)


def upgrade() -> None:
    """Create recipes, copy data over, and slim posts down to Instagram-only fields."""

    op.create_table(
        "recipes",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("timestamp_utc", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("recipe_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("recipe_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="lizapanelim"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recipes_timestamp_utc"), "recipes", ["timestamp_utc"])

    connection = op.get_bind()
    posts = connection.execute(sa.select(_OLD_POSTS)).mappings().all()
    if posts:
        connection.execute(
            sa.insert(_RECIPES),
            [
                {
                    "id": post["shortcode"],
                    "image_url": post["image_url"],
                    "caption": post["caption"],
                    "timestamp_utc": post["timestamp_utc"],
                    "title": post["title"],
                    "recipe_url": post["recipe_url"],
                    "recipe_name": next(iter(post["recipe_names"] or []), ""),
                    "source": post["source"],
                }
                for post in posts
            ],
        )

    connection.execute(sa.delete(_OLD_POSTS).where(_OLD_POSTS.c.url == ""))

    for column in (
        "image_url", "caption", "timestamp_utc", "title", "recipe_url",
        "recipe_urls", "recipe_names", "source", "likes", "comments",
    ):
        op.drop_column("posts", column)

    op.create_foreign_key("fk_posts_shortcode_recipes", "posts", "recipes", ["shortcode"], ["id"])


def downgrade() -> None:
    """Restore the flat posts shape and drop recipes."""

    op.drop_constraint("fk_posts_shortcode_recipes", "posts", type_="foreignkey")
    op.add_column("posts", sa.Column("image_url", sa.Text(), nullable=False, server_default=""))
    op.add_column("posts", sa.Column("caption", sa.Text(), nullable=False, server_default=""))
    op.add_column("posts", sa.Column("timestamp_utc", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("posts", sa.Column("title", sa.Text(), nullable=False, server_default=""))
    op.add_column("posts", sa.Column("recipe_url", sa.Text(), nullable=False, server_default=""))
    op.add_column("posts", sa.Column("recipe_urls", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("posts", sa.Column("recipe_names", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("posts", sa.Column("source", sa.String(length=32), nullable=False, server_default="lizapanelim"))
    op.add_column("posts", sa.Column("likes", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("posts", sa.Column("comments", sa.Integer(), nullable=False, server_default="0"))

    connection = op.get_bind()
    recipes = connection.execute(sa.select(_RECIPES)).mappings().all()
    existing_shortcodes = {row[0] for row in connection.execute(sa.select(_NEW_POSTS.c.shortcode))}

    old_posts_full = sa.table(
        "posts",
        *(column.copy() for column in _NEW_POSTS.columns),
        sa.column("image_url", sa.Text()),
        sa.column("caption", sa.Text()),
        sa.column("timestamp_utc", sa.String(length=64)),
        sa.column("title", sa.Text()),
        sa.column("recipe_url", sa.Text()),
        sa.column("recipe_urls", sa.JSON()),
        sa.column("recipe_names", sa.JSON()),
        sa.column("source", sa.String(length=32)),
        sa.column("likes", sa.Integer()),
        sa.column("comments", sa.Integer()),
    )

    for recipe in recipes:
        recipe_names = [recipe["recipe_name"]] if recipe["recipe_name"] else []
        common = {
            "image_url": recipe["image_url"],
            "caption": recipe["caption"],
            "timestamp_utc": recipe["timestamp_utc"],
            "title": recipe["title"],
            "recipe_url": recipe["recipe_url"],
            "recipe_urls": [],
            "recipe_names": recipe_names,
            "source": recipe["source"],
        }
        if recipe["id"] in existing_shortcodes:
            connection.execute(
                sa.update(old_posts_full).where(old_posts_full.c.shortcode == recipe["id"]).values(**common)
            )
        else:
            # A recipe with no matching post (e.g. hand-curated, non-Instagram) --
            # recreate it as a blank-Instagram-fields post to restore the old table shape.
            connection.execute(
                sa.insert(old_posts_full),
                [
                    {
                        "shortcode": recipe["id"],
                        "url": "",
                        "typename": "",
                        "is_video": False,
                        "is_recipe": True,
                        "likes": 0,
                        "comments": 0,
                        **common,
                    }
                ],
            )

    op.drop_table("recipes")
