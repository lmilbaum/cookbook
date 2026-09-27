"""Unify custom and imported recipes in the recipes table."""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "20260927_01"
down_revision = "20260925_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add added_via column, migrate custom recipes from recipe_states to recipes table."""

    # Add column
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(
            sa.Column("added_via", sa.String(16), nullable=False, server_default="instagram")
        )
        batch_op.create_check_constraint(
            "ck_recipes_added_via",
            "added_via IN ('instagram','website','custom')"
        )

    # Backfill: instagram for recipes with posts, website for others
    connection = op.get_bind()
    posted_ids = {row[0] for row in connection.execute(sa.text("SELECT shortcode FROM posts"))}
    recipes = connection.execute(
        sa.text("SELECT id FROM recipes WHERE added_via = 'instagram'")
    ).fetchall()

    for (recipe_id,) in recipes:
        added_via = "instagram" if recipe_id in posted_ids else "website"
        if added_via != "instagram":
            connection.execute(
                sa.text("UPDATE recipes SET added_via = :added_via WHERE id = :id"),
                {"added_via": added_via, "id": recipe_id},
            )

    # Migrate custom recipes from recipe_states to recipes table
    recipe_states = connection.execute(
        sa.text("SELECT id, payload FROM recipe_states ORDER BY id")
    ).fetchall()

    for state_id, payload_str in recipe_states:
        if not payload_str:
            continue

        payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        if "custom" not in payload or not payload["custom"]:
            continue

        custom_recipes = payload["custom"]
        overrides = payload.get("overrides", {})

        for custom_recipe in custom_recipes:
            recipe_id = custom_recipe.get("id")
            if not recipe_id:
                continue

            # Skip if recipe already exists
            existing = connection.execute(
                sa.text("SELECT id FROM recipes WHERE id = :id"),
                {"id": recipe_id}
            ).fetchone()
            if existing:
                continue

            # Insert custom recipe into recipes table
            connection.execute(
                sa.text(
                    "INSERT INTO recipes "
                    "(id, image_url, caption, timestamp_utc, title, recipe_url, recipe_name, source, source_name, added_via) "
                    "VALUES (:id, :image_url, :caption, :timestamp_utc, :title, :recipe_url, :recipe_name, :source, :source_name, :added_via)"
                ),
                {
                    "id": recipe_id,
                    "image_url": custom_recipe.get("imageUrl", ""),
                    "caption": "",
                    "timestamp_utc": custom_recipe.get("timestamp", ""),
                    "title": custom_recipe.get("title", ""),
                    "recipe_url": custom_recipe.get("recipeUrl", ""),
                    "recipe_name": custom_recipe.get("recipeName", ""),
                    "source": custom_recipe.get("source", "unknown"),
                    "source_name": custom_recipe.get("sourceName", ""),
                    "added_via": "custom",
                }
            )

            # Move custom recipe to overrides
            overrides[recipe_id] = custom_recipe

        # Clear custom array and bump revision
        updated_payload = {
            "overrides": overrides,
            "custom": [],
            "order": payload.get("order", []),
            "types": payload.get("types", []),
        }
        connection.execute(
            sa.text("UPDATE recipe_states SET payload = :payload, revision = revision + 1 WHERE id = :id"),
            {"payload": json.dumps(updated_payload), "id": state_id}
        )


def downgrade() -> None:
    """Reverse: restore custom recipes to recipe_states, delete custom recipe rows."""

    connection = op.get_bind()

    # Read all recipe_states
    recipe_states = connection.execute(
        sa.text("SELECT id, payload FROM recipe_states ORDER BY id")
    ).fetchall()

    for state_id, payload_str in recipe_states:
        if not payload_str:
            continue

        payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        overrides = payload.get("overrides", {})
        custom = []

        # Find custom recipes in overrides
        custom_ids = connection.execute(
            sa.text("SELECT id FROM recipes WHERE added_via = 'custom'")
        ).fetchall()

        for (recipe_id,) in custom_ids:
            if recipe_id in overrides:
                custom.append(overrides[recipe_id])
                del overrides[recipe_id]

        # Update recipe_states
        updated_payload = {
            "overrides": overrides,
            "custom": custom,
            "order": payload.get("order", []),
            "types": payload.get("types", []),
        }
        connection.execute(
            sa.text("UPDATE recipe_states SET payload = :payload, revision = revision + 1 WHERE id = :id"),
            {"payload": json.dumps(updated_payload), "id": state_id}
        )

    # Delete custom recipe rows
    connection.execute(sa.text("DELETE FROM recipes WHERE added_via = 'custom'"))

    # Drop check constraint and column
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_constraint("ck_recipes_added_via", type_="check")
        batch_op.drop_column("added_via")
