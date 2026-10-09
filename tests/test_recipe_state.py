"""Recipe state migration, validation, and HTTP concurrency tests."""
from __future__ import annotations

import io
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from cookbook import server
from cookbook.models import Recipe, RecipeState
from cookbook.recipe_state_repository import load_recipe_state, valid_state


@pytest.fixture
def storage():
    from cookbook.database import Base
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


def test_api_preserves_edits_and_rejects_stale_saves(storage, tmp_path, monkeypatch):
    handler = object.__new__(server.make_handler(tmp_path, storage))
    handler.path = "/api/recipe-state"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    def get():
        handler.do_GET()
        return responses.pop()

    def put(state, revision):
        body = json.dumps({"state": state, "revision": revision}).encode()
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.do_PUT()
        return responses.pop()

    # Seed a recipe row for "post" so the pruning logic doesn't drop it
    from cookbook.database import session_scope
    from cookbook.models import Recipe as RecipeModel
    with session_scope(storage) as session:
        session.add(RecipeModel(
            id="post", image_url="", caption="", timestamp_utc="2026-01-01T00:00:00Z",
            title="Test Post", recipe_url="", recipe_name="", source="lizapanelim",
            source_name="", added_via="instagram",
        ))

    empty = {"overrides": {}, "custom": []}
    assert get() == (200, {"revision": 0, "state": empty})
    state = {"overrides": {"post": {"notes": "הערות", "title": "Edited"}},
             "custom": [{"id": "custom-1", "title": "Soup", "ingredients": [
                 {"name": "Salt", "amount": "1", "varieties": "Sea"}]}],
             "order": ["custom-1", "post"]}
    assert put(state, 0) == (200, {"revision": 1})
    assert put(empty, 0)[0] == 409
    assert put({"overrides": [], "custom": []}, 1)[0] == 400
    assert put(empty, True)[0] == 400
    # After migration, custom items are moved to overrides and custom is cleared
    migrated_state = {"overrides": {"post": {"notes": "הערות", "title": "Edited"},
                                    "custom-1": {"id": "custom-1", "title": "Soup", "ingredients": [
                                        {"name": "Salt", "amount": "1", "varieties": "Sea"}]}},
                      "custom": [], "order": ["custom-1", "post"]}
    assert get() == (200, {"revision": 1, "state": migrated_state})
    assert put(empty, 1) == (200, {"revision": 2})
    # custom-1 still exists in the DB, so load_recipe_state re-appends it to order
    assert get() == (200, {"revision": 2, "state": {**empty, "order": ["custom-1"]}})
    assert put(state, 0)[0] == 409  # Never reimport after an intentional clear.

    def unavailable(*args):
        raise SQLAlchemyError("private connection details")

    monkeypatch.setattr(server, "save_recipe_state", unavailable)
    assert put(state, 2) == (503, {"error": "Unable to save recipe state"})
    monkeypatch.setattr(server, "load_recipe_state", unavailable)
    assert get() == (503, {"error": "Unable to read recipe state"})


@pytest.mark.parametrize("state", [
    None, [], {}, {"overrides": {}, "custom": [None]},
    {"overrides": {"a": {"id": "b"}}, "custom": []},
    {"overrides": {}, "custom": [{"id": "x"}, {"id": "x"}]},
    {"overrides": {"a": {"notes": 1}}, "custom": []},
    {"overrides": {"a": {"ingredients": ["salt"]}}, "custom": []},
    {"overrides": {}, "custom": [], "order": "a"},
])
def test_invalid_state(state):
    assert not valid_state(state)


def test_saved_types_list_is_validated():
    base = {"overrides": {}, "custom": []}
    assert valid_state({**base, "types": ["סלט", "עוגה"]})
    assert not valid_state({**base, "types": "סלט"})
    assert not valid_state({**base, "types": ["סלט", 1]})
    assert not valid_state({**base, "types": ["  "]})


def test_load_recipe_state_appends_custom_recipes_missing_from_order(storage):
    """Custom recipes in the DB are always present in state.order.

    Regression for the bug where POST /api/recipes could succeed (saving the
    recipe row) but the browser's fetch timed out before receiving the 201,
    so state.order was never updated — leaving the recipe invisible in the grid.
    """
    from cookbook.database import session_scope

    # Persist a state without custom-orphan in its order
    with session_scope(storage) as session:
        session.add(RecipeState(id=1, revision=1, payload={"overrides": {}, "custom": [], "order": ["other-recipe"]}))
        # "other-recipe" must exist in the DB so pruning doesn't remove it
        session.add(Recipe(
            id="other-recipe", image_url="", caption="", timestamp_utc="2026-01-01T00:00:00Z",
            title="Other Recipe", recipe_url="", recipe_name="", source="lizapanelim",
            source_name="", added_via="instagram",
        ))
        # Simulate the race: recipe row exists in DB but state.order was never updated
        session.add(Recipe(
            id="custom-orphan", image_url="", caption="", timestamp_utc="2026-01-01T00:00:00Z",
            title="Orphan Recipe", recipe_url="", recipe_name="", source="unknown",
            source_name="", added_via="manual",
        ))

    result = load_recipe_state(storage)
    assert "custom-orphan" in result["state"]["order"]
    assert "other-recipe" in result["state"]["order"]
    # orphan appended after existing order entries
    assert result["state"]["order"].index("other-recipe") < result["state"]["order"].index("custom-orphan")


def test_recipes_saved_from_the_page_are_valid():
    """The page saves every recipe field, including source and type."""
    recipe = {
        "id": "r1", "title": "Soup", "sourceUrl": "", "source": "lizapanelim", "recipeUrl": "",
        "recipeName": "", "recipeUrls": [], "recipeNames": [], "imageUrl": "", "ingredients": [],
        "instructions": "", "type": "מרק", "prerequisiteId": "", "notes": "",
    }
    assert valid_state({"overrides": {"r1": recipe}, "custom": []})
    assert valid_state({"overrides": {}, "custom": [recipe]})
    assert not valid_state({"overrides": {"r1": {**recipe, "source": 1}}, "custom": []})


def test_fill_recipe_override_fills_missing_fields(storage):
    """fill_recipe_override should fill only blank fields in an override."""
    from cookbook.recipe_state_repository import fill_recipe_override

    # Seed initial state with revision 1
    from cookbook.database import session_scope

    with session_scope(storage) as session:
        session.add(
            RecipeState(
                id=1,
                revision=1,
                payload={"overrides": {}, "custom": []},
            )
        )

    fields = {"title": "Test Title", "ingredients": [{"name": "Salt", "amount": "1 tsp", "varieties": ""}]}
    result = fill_recipe_override(storage, "recipe1", fields)

    assert result is not None
    new_rev, written = result
    assert new_rev == 2
    assert "title" in written
    assert "ingredients" in written


def test_fill_recipe_override_keeps_non_empty_user_fields(storage):
    """fill_recipe_override should keep existing user-provided fields."""
    from cookbook.recipe_state_repository import fill_recipe_override

    from cookbook.database import session_scope

    with session_scope(storage) as session:
        session.add(
            RecipeState(
                id=1,
                revision=1,
                payload={
                    "overrides": {
                        "recipe1": {"id": "recipe1", "title": "User Title", "notes": "User Notes"}
                    },
                    "custom": [],
                },
            )
        )

    fields = {"title": "New Title", "instructions": "New Instructions"}
    result = fill_recipe_override(storage, "recipe1", fields)

    assert result is not None
    new_rev, written = result
    # Only fill blank fields, so title should not be in written (already user-provided)
    # instructions should be filled
    assert "instructions" in written
    # Title must not be overwritten since it already has a user-provided value
    assert "title" not in written

    # Verify that persisted state still has the original user title
    persisted = load_recipe_state(storage)
    assert persisted["state"]["overrides"]["recipe1"]["title"] == "User Title"


def test_fill_recipe_override_returns_none_on_revision_zero(storage):
    """fill_recipe_override should return None if revision is 0 (no state record)."""
    from cookbook.recipe_state_repository import fill_recipe_override

    # No state record → revision 0
    fields = {"title": "Test Title"}
    result = fill_recipe_override(storage, "recipe1", fields)

    assert result is None


def test_fill_recipe_override_retries_on_conflict(storage, monkeypatch):
    """fill_recipe_override should retry after RecipeStateConflict."""
    from cookbook.recipe_state_repository import fill_recipe_override, save_recipe_state, RecipeStateConflict

    from cookbook.database import session_scope

    with session_scope(storage) as session:
        session.add(
            RecipeState(
                id=1,
                revision=1,
                payload={"overrides": {}, "custom": []},
            )
        )

    call_count = [0]
    original_save = save_recipe_state

    def save_with_conflict_once(factory, state, revision):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RecipeStateConflict("Simulated conflict")
        return original_save(factory, state, revision)

    monkeypatch.setattr("cookbook.recipe_state_repository.save_recipe_state", save_with_conflict_once)

    fields = {"title": "Test Title"}
    result = fill_recipe_override(storage, "recipe1", fields, attempts=3)

    assert result is not None
    assert call_count[0] == 2  # Failed once, succeeded on retry


def test_image_url_overrides_keeps_only_http_urls() -> None:
    from cookbook.recipe_state_repository import image_url_overrides
    state = {
        "overrides": {
            "a": {"id": "a", "imageUrl": " https://x/a.jpg "},
            "b": {"id": "b", "imageUrl": ""},
            "c": {"id": "c", "imageUrl": "recipes/photos/c"},
            "d": {"id": "d", "imageUrl": "/liza_posts_assets/d.jpg"},
            "e": {"id": "e"},
        },
        "custom": [],
    }
    result = image_url_overrides(state)
    assert result == {"a": "https://x/a.jpg"}


def test_put_recipe_state_requests_replacement_for_changed_image_url(tmp_path, storage) -> None:
    replacements = []

    class FakeBackfill:
        def request_replacements(self, urls):
            replacements.append(dict(urls))

    handler = object.__new__(server.make_handler(tmp_path, storage, photo_backfill=FakeBackfill()))
    handler.path = "/api/recipe-state"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    def put(state, revision):
        body = json.dumps({"state": state, "revision": revision}).encode()
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.do_PUT()
        return responses.pop()

    from cookbook.database import session_scope
    from cookbook.post_repository import create_manual_recipe
    recipe = create_manual_recipe("test")
    rid = recipe.id
    with session_scope(storage) as s:
        s.add(recipe)

    url = "https://cdn.example/1.jpg"
    state = {"overrides": {rid: {"id": rid, "imageUrl": url, "title": "First"}}, "custom": [], "order": [rid]}
    assert put(state, 0) == (200, {"revision": 1})
    assert replacements == [{rid: url}]

    # Same image URL with a different title does not trigger another download.
    state = {"overrides": {rid: {"id": rid, "imageUrl": url, "title": "Second"}}, "custom": [], "order": [rid]}
    assert put(state, 1) == (200, {"revision": 2})
    assert len(replacements) == 1

    # Non-downloadable local paths never trigger a download.
    state = {"overrides": {rid: {"id": rid, "imageUrl": f"recipes/photos/{rid}", "title": "Second"}},
             "custom": [], "order": [rid]}
    assert put(state, 2) == (200, {"revision": 3})
    assert len(replacements) == 1
