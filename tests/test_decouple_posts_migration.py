"""Migration test: dropping the posts->recipes foreign key."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def _load_migration():
    path = Path(__file__).parents[1] / "migrations/versions/20260918_01_decouple_posts_from_recipes.py"
    spec = importlib.util.spec_from_file_location("decouple_posts_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _create_pre_migration_schema(connection: sa.Connection) -> None:
    connection.execute(sa.text(
        "CREATE TABLE recipes (id TEXT PRIMARY KEY, image_url TEXT NOT NULL,"
        " caption TEXT NOT NULL, timestamp_utc TEXT NOT NULL,"
        " title TEXT NOT NULL DEFAULT '', recipe_url TEXT NOT NULL DEFAULT '',"
        " recipe_name TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'lizapanelim')"
    ))
    connection.execute(sa.text(
        "CREATE TABLE posts (shortcode TEXT PRIMARY KEY, url TEXT NOT NULL,"
        " typename TEXT NOT NULL, is_video BOOLEAN NOT NULL,"
        " is_recipe BOOLEAN NOT NULL DEFAULT 1, source TEXT NOT NULL DEFAULT 'lizapanelim',"
        " CONSTRAINT fk_posts_shortcode_recipes FOREIGN KEY(shortcode) REFERENCES recipes(id))"
    ))


def test_upgrade_drops_fk_and_deletes_already_hidden_recipes() -> None:
    migration = _load_migration()
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        _create_pre_migration_schema(connection)
        connection.execute(sa.text(
            "INSERT INTO recipes (id, image_url, caption, timestamp_utc) VALUES"
            " ('visible', '', '', 't'), ('hidden', '', '', 't')"
        ))
        connection.execute(sa.text(
            "INSERT INTO posts (shortcode, url, typename, is_video, is_recipe) VALUES"
            " ('visible', 'u', 'GraphImage', 0, 1), ('hidden', 'u', 'GraphImage', 0, 0)"
        ))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    with engine.connect() as connection:
        remaining_recipes = {row[0] for row in connection.execute(sa.text("SELECT id FROM recipes"))}
        assert remaining_recipes == {"visible"}
        remaining_posts = {row[0] for row in connection.execute(sa.text("SELECT shortcode FROM posts"))}
        assert remaining_posts == {"visible", "hidden"}
        foreign_keys = inspect(connection).get_foreign_keys("posts")
        assert foreign_keys == []
    engine.dispose()


def test_downgrade_restores_fk_and_recreates_orphaned_recipes() -> None:
    migration = _load_migration()
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        _create_pre_migration_schema(connection)
        connection.execute(sa.text(
            "INSERT INTO recipes (id, image_url, caption, timestamp_utc) VALUES ('visible', '', '', 't')"
        ))
        connection.execute(sa.text(
            "INSERT INTO posts (shortcode, url, typename, is_video, is_recipe) VALUES"
            " ('visible', 'u', 'GraphImage', 0, 1), ('hidden', 'u', 'GraphImage', 0, 0)"
        ))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

    with engine.connect() as connection:
        remaining_recipes = {row[0] for row in connection.execute(sa.text("SELECT id FROM recipes"))}
        assert remaining_recipes == {"visible", "hidden"}
        foreign_keys = inspect(connection).get_foreign_keys("posts")
        assert len(foreign_keys) == 1
        assert foreign_keys[0]["referred_table"] == "recipes"
    engine.dispose()
