"""Check explicit recipe-state imports preserve both source and existing edits."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from cookbook import recipe_state_import
from cookbook.database import Base
from cookbook.recipe_state_repository import load_recipe_state, save_recipe_state


@pytest.fixture
def importer(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    source = tmp_path / "recipe-state.json"
    monkeypatch.setattr(recipe_state_import, "create_session_factory", lambda: factory)
    monkeypatch.setattr(recipe_state_import, "load_dotenv", lambda: None)
    monkeypatch.setattr("sys.argv", ["import", "--file", str(source)])
    yield source, factory
    engine.dispose()


def test_import_preserves_complete_state_and_source(importer):
    source, factory = importer
    state = {
        "overrides": {"post": {"title": "מרק", "notes": "Family recipe"}},
        "custom": [{"id": "custom-1", "title": "Soup", "ingredients": [
            {"name": "Salt", "amount": "1", "varieties": "Sea"}],
            "instructions": "Mix", "prerequisiteId": "post"}],
        "order": ["custom-1", "post"],
    }
    original = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    source.write_text(original, encoding="utf-8")
    recipe_state_import.main()
    assert load_recipe_state(factory) == {"revision": 1, "state": state}
    with pytest.raises(SystemExit) as error:
        recipe_state_import.main()
    assert error.value.code == 2
    assert load_recipe_state(factory) == {"revision": 1, "state": state}
    assert source.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("content", [None, b"\xff", b"{", b"[]", b'{"overrides":{},"custom":[{}]}'])
def test_invalid_input_never_initializes_state(importer, content):
    source, factory = importer
    if content is not None:
        source.write_bytes(content)
    with pytest.raises(SystemExit) as error:
        recipe_state_import.main()
    assert error.value.code == 2
    assert load_recipe_state(factory)["revision"] == 0
    if content is not None:
        assert source.read_bytes() == content


def test_empty_import_prevents_later_reimport(importer):
    source, factory = importer
    empty = {"overrides": {}, "custom": []}
    source.write_text(json.dumps(empty))
    recipe_state_import.main()
    save_recipe_state(factory, empty, revision=1)
    source.write_text(json.dumps({"overrides": {"post": {"notes": "Old"}}, "custom": []}))
    with pytest.raises(SystemExit):
        recipe_state_import.main()
    assert load_recipe_state(factory) == {"revision": 2, "state": empty}


def test_database_errors_do_not_expose_connection_details(importer, monkeypatch, capsys):
    source, factory = importer
    source.write_text('{"overrides":{},"custom":[]}')

    def unavailable(*args, **kwargs):
        raise SQLAlchemyError("private connection details")

    monkeypatch.setattr(recipe_state_import, "save_recipe_state", unavailable)
    with pytest.raises(SystemExit) as error:
        recipe_state_import.main()
    assert error.value.code == 2
    assert "private connection details" not in capsys.readouterr().err
    assert load_recipe_state(factory)["revision"] == 0
