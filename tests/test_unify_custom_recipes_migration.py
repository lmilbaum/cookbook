"""Test the migration that unifies custom and imported recipes."""

from __future__ import annotations

import json

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from migration_helpers import load_migration
from sqlalchemy import create_engine, text

from cookbook.models import Post, Recipe, RecipeState

_MIGRATION = "20260927_01_unify_custom_recipes.py"


def _create_pre_migration_schema(connection: object) -> None:
    """Create the recipes table schema as it was before the migration that adds added_via."""
    connection.execute(text(
        "CREATE TABLE recipes ("
        "id TEXT PRIMARY KEY, "
        "image_url TEXT NOT NULL, "
        "caption TEXT NOT NULL, "
        "timestamp_utc TEXT NOT NULL, "
        "title TEXT NOT NULL DEFAULT '', "
        "recipe_url TEXT NOT NULL DEFAULT '', "
        "recipe_name TEXT NOT NULL DEFAULT '', "
        "source TEXT NOT NULL DEFAULT 'lizapanelim', "
        "source_name TEXT NOT NULL DEFAULT '')"
    ))
    connection.execute(text(
        "CREATE TABLE posts ("
        "shortcode TEXT PRIMARY KEY, "
        "url TEXT NOT NULL, "
        "typename TEXT NOT NULL, "
        "is_video BOOLEAN NOT NULL, "
        "is_recipe BOOLEAN NOT NULL DEFAULT 1)"
    ))
    connection.execute(text(
        "CREATE TABLE recipe_states ("
        "id INTEGER PRIMARY KEY, "
        "revision INTEGER NOT NULL, "
        "payload JSON NOT NULL)"
    ))


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        _create_pre_migration_schema(connection)
    return engine


def _run(engine, downgrade: bool = False) -> None:
    migration = load_migration(_MIGRATION)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        (migration.downgrade if downgrade else migration.upgrade)()


def test_upgrade_adds_added_via_column(engine):
    """After upgrade, recipes have an added_via column."""
    # Insert a post and a recipe
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO posts (shortcode, url, typename, is_video, is_recipe) "
                "VALUES ('test1', 'https://instagram.com/p/test1', 'GraphImage', 0, 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO recipes (id, image_url, caption, timestamp_utc, title, recipe_url, recipe_name, source, source_name) "
                "VALUES ('test1', '', 'caption', '2026-09-01T00:00:00Z', 'Test', '', '', 'unknown', '')"
            )
        )

    _run(engine)

    with engine.connect() as conn:
        # Check that added_via column exists and has a value
        result = conn.execute(text("SELECT added_via FROM recipes WHERE id = 'test1'"))
        assert result.scalar() == "instagram"


def test_upgrade_backfills_instagram_for_recipes_with_posts(engine):
    """Recipes with posts get added_via='instagram'."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO posts (shortcode, url, typename, is_video, is_recipe) "
                "VALUES ('abc123', 'https://instagram.com/p/abc123', 'GraphImage', 0, 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO recipes (id, image_url, caption, timestamp_utc, title, recipe_url, recipe_name, source, source_name) "
                "VALUES ('abc123', '', '', '2026-09-01T00:00:00Z', 'Test', '', '', 'unknown', '')"
            )
        )

    _run(engine)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT added_via FROM recipes WHERE id = 'abc123'"))
        assert result.scalar() == "instagram"


def test_upgrade_backfills_website_for_recipes_without_posts(engine):
    """Recipes without posts get added_via='website'."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO recipes (id, image_url, caption, timestamp_utc, title, recipe_url, recipe_name, source, source_name) "
                "VALUES ('manual1', '', '', '2026-09-01T00:00:00Z', 'Manual', '', '', 'unknown', '')"
            )
        )

    _run(engine)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT added_via FROM recipes WHERE id = 'manual1'"))
        assert result.scalar() == "website"


def test_upgrade_migrates_custom_recipes_to_recipes_table(engine):
    """Custom recipes in recipe_states migrate to the recipes table."""
    custom_recipe = {
        "id": "custom-1234567890-deadbeef",
        "title": "Custom Recipe",
        "recipeUrl": "https://example.com/recipe",
        "recipeName": "Custom Recipe",
        "imageUrl": "https://example.com/image.jpg",
        "source": "unknown",
        "sourceName": "",
        "timestamp": "2026-09-01T00:00:00Z",
        "ingredients": [],
        "instructions": "",
        "type": "unknown",
        "prerequisiteId": "",
        "notes": "",
    }
    payload = {
        "overrides": {},
        "custom": [custom_recipe],
        "order": [],
        "types": [],
    }
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO recipe_states (id, revision, payload) VALUES (1, 1, :p)"),
            {"p": json.dumps(payload)}
        )

    _run(engine)

    with engine.connect() as conn:
        # Check recipe was inserted
        result = conn.execute(
            text("SELECT added_via FROM recipes WHERE id = 'custom-1234567890-deadbeef'")
        )
        assert result.scalar() == "custom"

        # Check recipe_states was updated
        result = conn.execute(text("SELECT payload FROM recipe_states WHERE id = 1"))
        payload = json.loads(result.scalar())
        assert payload["custom"] == []
        assert "custom-1234567890-deadbeef" in payload["overrides"]
        assert payload["overrides"]["custom-1234567890-deadbeef"]["title"] == "Custom Recipe"


def test_downgrade_restores_custom_recipes():
    """Downgrade removes added_via column, restores custom recipes to recipe_states."""
    # Create a fresh engine for this test
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        _create_pre_migration_schema(connection)

    # Seed with pre-migration schema
    custom_recipe_dict = {
        "id": "custom-1234567890-deadbeef",
        "title": "Custom Recipe",
        "recipeUrl": "https://example.com/recipe",
        "recipeName": "Custom Recipe",
        "imageUrl": "https://example.com/image.jpg",
        "source": "unknown",
        "sourceName": "",
        "timestamp": "2026-09-01T00:00:00Z",
        "ingredients": [],
        "instructions": "",
        "type": "unknown",
        "prerequisiteId": "",
        "notes": "",
    }
    imported_recipe_dict = {"id": "imported-1", "title": "Imported Recipe"}
    payload = {
        "overrides": {"imported-1": imported_recipe_dict},
        "custom": [custom_recipe_dict],  # Custom recipes start in the custom array
        "order": ["imported-1", "custom-1234567890-deadbeef"],
        "types": [],
    }

    with engine.begin() as conn:
        # Insert imported recipe
        conn.execute(
            text(
                "INSERT INTO recipes (id, image_url, caption, timestamp_utc, title, recipe_url, recipe_name, source, source_name) "
                "VALUES ('imported-1', '', '', '2026-09-01T00:00:00Z', 'Imported Recipe', '', '', 'unknown', '')"
            )
        )
        # Insert recipe_state with custom recipe in custom array
        conn.execute(
            text("INSERT INTO recipe_states (id, revision, payload) VALUES (1, 1, :p)"),
            {"p": json.dumps(payload)}
        )

    # Run upgrade
    _run(engine)

    with engine.connect() as conn:
        # After upgrade, verify structure
        result = conn.execute(text("SELECT added_via FROM recipes WHERE id = 'custom-1234567890-deadbeef'"))
        assert result.scalar() == "custom"
        result = conn.execute(text("SELECT revision FROM recipe_states WHERE id = 1"))
        assert result.scalar() == 2  # revision was bumped

    # Run downgrade
    _run(engine, downgrade=True)

    with engine.connect() as conn:
        # Check added_via column no longer exists
        try:
            conn.execute(text("SELECT added_via FROM recipes WHERE id = 'custom-1234567890-deadbeef'"))
            assert False, "added_via column should not exist after downgrade"
        except Exception:
            pass  # Expected - column doesn't exist

        # Check custom recipe was deleted from recipes table
        result = conn.execute(
            text("SELECT id FROM recipes WHERE id = 'custom-1234567890-deadbeef'")
        )
        assert result.scalar() is None

        # Check custom recipe is back in recipe_states.payload["custom"]
        result = conn.execute(text("SELECT revision, payload FROM recipe_states WHERE id = 1"))
        revision, payload_str = result.one()
        payload = json.loads(payload_str)
        assert revision == 3  # Bumped again on downgrade
        assert len(payload["custom"]) == 1
        assert payload["custom"][0]["id"] == "custom-1234567890-deadbeef"
        assert payload["custom"][0]["title"] == "Custom Recipe"

        # Check custom recipe is no longer in overrides
        assert "custom-1234567890-deadbeef" not in payload["overrides"]

        # Check imported recipe is still there
        assert "imported-1" in payload["overrides"]
