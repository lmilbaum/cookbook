"""The stored recipe source "other" is renamed to "unknown" by migration 20260919_03."""

from __future__ import annotations

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from migration_helpers import load_migration
from sqlalchemy import create_engine, text

from cookbook.models import Recipe, RecipeState

_MIGRATION = "20260919_03_rename_source_other_to_unknown.py"


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    for model in (Recipe, RecipeState):
        model.__table__.create(engine)
    with engine.begin() as connection:
        for recipe_id, source in [("a", "other"), ("b", "lizapanelim"), ("c", "other")]:
            connection.execute(
                text("INSERT INTO recipes (id, image_url, caption, timestamp_utc, title, recipe_url, recipe_name, source)"
                     " VALUES (:id, '', '', 't', '', '', '', :source)"),
                {"id": recipe_id, "source": source},
            )
    return engine


def _run(engine, downgrade: bool = False) -> None:
    migration = load_migration(_MIGRATION)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        (migration.downgrade if downgrade else migration.upgrade)()


def _sources(engine) -> dict[str, str]:
    with engine.connect() as connection:
        return dict(connection.execute(text("SELECT id, source FROM recipes")).fetchall())


def test_recipe_sources_are_renamed_and_can_be_restored(engine) -> None:
    _run(engine)
    assert _sources(engine) == {"a": "unknown", "b": "lizapanelim", "c": "unknown"}
    _run(engine, downgrade=True)
    assert _sources(engine) == {"a": "other", "b": "lizapanelim", "c": "other"}


def test_saved_recipe_edits_are_renamed_and_the_revision_bumped(engine) -> None:
    import json

    payload = {
        "overrides": {"a": {"id": "a", "source": "other"}, "b": {"id": "b", "source": "lizapanelim"}},
        "custom": [{"id": "custom-1", "source": "other"}, {"id": "custom-2"}],
        "order": ["a", "b"],
    }
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO recipe_states (id, revision, payload) VALUES (1, 4, :p)"),
                           {"p": json.dumps(payload)})

    _run(engine)
    with engine.connect() as connection:
        revision, saved = connection.execute(text("SELECT revision, payload FROM recipe_states")).one()
    saved = json.loads(saved) if isinstance(saved, str) else saved
    assert revision == 5  # stale tabs must conflict rather than write "other" back
    assert saved["overrides"]["a"]["source"] == "unknown"
    assert saved["overrides"]["b"]["source"] == "lizapanelim"
    assert saved["custom"][0]["source"] == "unknown"
    assert "source" not in saved["custom"][1]
    assert saved["order"] == ["a", "b"]


def test_untouched_recipe_state_keeps_its_revision(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO recipe_states (id, revision, payload) VALUES (1, 4, :p)"),
                           {"p": '{"overrides": {}, "custom": []}'})
    _run(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT revision FROM recipe_states")).scalar() == 4
