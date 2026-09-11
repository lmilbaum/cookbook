"""Validate the explicit legacy import without changing source data."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cookbook import shopping_list_import
from cookbook.database import Base
from cookbook.shopping_list_repository import load_shopping_list


def test_import_command_preserves_source_and_rejects_bad_payload(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(shopping_list_import, "create_session_factory", lambda: factory)
    monkeypatch.setattr(shopping_list_import, "load_dotenv", lambda: None)
    source = tmp_path / "shopping_list.json"
    monkeypatch.setattr("sys.argv", ["import", "--file", str(source)])
    source.write_text('{"not": "a list"}')
    with pytest.raises(SystemExit) as error:
        shopping_list_import.main()
    assert error.value.code == 2
    assert load_shopping_list(factory) == []
    payload = [{"id": "milk", "name": "חלב", "done": False}]
    original = json.dumps(payload, ensure_ascii=False)
    source.write_text(original, encoding="utf-8")
    shopping_list_import.main()
    assert source.read_text(encoding="utf-8") == original
    assert load_shopping_list(factory) == payload
    with pytest.raises(SystemExit):
        shopping_list_import.main()
    assert load_shopping_list(factory) == payload
    engine.dispose()
