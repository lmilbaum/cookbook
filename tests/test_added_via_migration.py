"""Regression coverage for simplifying recipe origin values."""

from __future__ import annotations

from alembic.migration import MigrationContext
from alembic.operations import Operations
from migration_helpers import load_migration
from sqlalchemy import create_engine, text

_MIGRATION = "20260928_01_simplify_added_via.py"


def _run(engine, *, downgrade: bool = False) -> None:
    migration = load_migration(_MIGRATION)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        (migration.downgrade if downgrade else migration.upgrade)()


def test_upgrade_maps_website_and_custom_to_manual(tmp_path) -> None:
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE recipes (id TEXT PRIMARY KEY, added_via VARCHAR(16) NOT NULL, "
            "CONSTRAINT ck_recipes_added_via CHECK "
            "(added_via IN ('instagram','website','custom')))"
        ))
        connection.execute(text(
            "INSERT INTO recipes (id, added_via) VALUES "
            "('from-site', 'website'), ('custom-one', 'custom'), ('post-one', 'instagram')"
        ))

    _run(engine)

    with engine.connect() as connection:
        values = dict(connection.execute(text("SELECT id, added_via FROM recipes")).fetchall())
        assert values == {
            "from-site": "manual", "custom-one": "manual", "post-one": "instagram"
        }

        constraint_sql = connection.scalar(text(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'recipes'"
        ))
        assert "'instagram','manual'" in constraint_sql

    _run(engine, downgrade=True)
    with engine.connect() as connection:
        values = dict(connection.execute(text("SELECT id, added_via FROM recipes")).fetchall())
        assert values == {
            "from-site": "website", "custom-one": "custom", "post-one": "instagram"
        }

    engine.dispose()
