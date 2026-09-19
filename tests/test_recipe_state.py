"""Recipe state migration, validation, and HTTP concurrency tests."""
from __future__ import annotations

import io
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from cookbook import server
from cookbook.models import RecipeState
from cookbook.recipe_state_repository import valid_state


@pytest.fixture
def storage():
    engine = create_engine("sqlite://")
    RecipeState.__table__.create(engine)
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
    assert get() == (200, {"revision": 1, "state": state})
    assert put(empty, 1) == (200, {"revision": 2})
    assert get() == (200, {"revision": 2, "state": empty})
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
