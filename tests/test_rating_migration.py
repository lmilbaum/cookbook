"""Regression coverage for the recipe_ratings table migration."""

from __future__ import annotations

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from migration_helpers import load_migration
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

_MIGRATION = "20261019_01_recipe_ratings.py"


def _run(engine, *, downgrade: bool = False) -> None:
    migration = load_migration(_MIGRATION)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        (migration.downgrade if downgrade else migration.upgrade)()


def test_upgrade_creates_table_that_only_accepts_up_and_down() -> None:
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE recipes (id TEXT PRIMARY KEY)"))
        connection.execute(text("INSERT INTO recipes (id) VALUES ('r1')"))
        connection.execute(text("INSERT INTO recipes (id) VALUES ('r2')"))

    _run(engine)

    with engine.begin() as connection:
        connection.execute(text("INSERT INTO recipe_ratings (recipe_id, rating) VALUES ('r1', 'up')"))

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("INSERT INTO recipe_ratings (recipe_id, rating) VALUES ('r2', 'meh')"))

    engine.dispose()


def test_downgrade_removes_table() -> None:
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE recipes (id TEXT PRIMARY KEY)"))

    _run(engine)
    assert "recipe_ratings" in inspect(engine).get_table_names()

    _run(engine, downgrade=True)
    assert "recipe_ratings" not in inspect(engine).get_table_names()

    engine.dispose()
