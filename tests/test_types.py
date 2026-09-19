"""Types table migration, repository and HTTP API tests without a running database."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from migration_helpers import RENAME_TABLES, load_migration
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cookbook.models import RecipeType
from cookbook.server import make_handler
from cookbook.type_repository import (
    DuplicateType,
    create_type,
    delete_type,
    get_type,
    list_types,
    rename_type,
)


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    RecipeType.__table__.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _apply(engine, *filenames: str, downgrade: bool = False) -> None:
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        for filename in filenames:
            migration = load_migration(filename)
            (migration.downgrade if downgrade else migration.upgrade)()


def test_tables_are_renamed_to_match_models_and_keep_their_data() -> None:
    engine = create_engine("sqlite://")
    _apply(engine, "20260911_01_shopping_lists.py", "20260913_01_recipe_state.py", "20260914_01_shopping_revision.py", "20260919_01_types.py")
    assert {"types", "shopping_list", "recipe_state", "shopping_list_state", "ingredients"} <= set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO types (name) VALUES ('סלט')")
        connection.exec_driver_sql("INSERT INTO ingredients (name) VALUES ('x')")
        connection.exec_driver_sql("INSERT INTO shopping_list (id, ingredient_id, done) VALUES ('a', 1, 0)")

    _apply(engine, RENAME_TABLES)
    tables = set(inspect(engine).get_table_names())
    assert {"recipe_types", "shopping_list_items", "recipe_states", "shopping_list_states"} <= tables
    assert not {"types", "shopping_list", "recipe_state", "shopping_list_state"} & tables
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT name FROM recipe_types").scalar() == "סלט"
        assert connection.exec_driver_sql("SELECT id FROM shopping_list_items").scalar() == "a"

    _apply(engine, RENAME_TABLES, downgrade=True)
    assert {"types", "shopping_list", "recipe_state"} <= set(inspect(engine).get_table_names())


def test_model_table_names_follow_the_plural_of_the_class_name() -> None:
    import cookbook.models  # noqa: F401  (registers the tables)
    from cookbook.database import Base

    def plural(name: str) -> str:
        snake = "".join(f"_{c.lower()}" if c.isupper() else c for c in name).lstrip("_")
        return snake + "s"

    for mapper in Base.registry.mappers:
        assert mapper.local_table.name == plural(mapper.class_.__name__)


def test_repository_crud(factory) -> None:
    salad = create_type(factory, "  סלט ")
    cake = create_type(factory, "עוגה")
    assert salad["name"] == "סלט"
    assert [t["name"] for t in list_types(factory)] == ["סלט", "עוגה"]
    assert get_type(factory, cake["id"]) == cake
    assert rename_type(factory, cake["id"], "מאפה") == {"id": cake["id"], "name": "מאפה"}
    assert delete_type(factory, cake["id"]) is True
    assert get_type(factory, cake["id"]) is None
    assert delete_type(factory, cake["id"]) is False
    assert rename_type(factory, 999, "x") is None


def test_repository_rejects_duplicates_and_bad_names(factory) -> None:
    create_type(factory, "סלט")
    with pytest.raises(DuplicateType):
        create_type(factory, "סלט")
    other = create_type(factory, "מרק")
    with pytest.raises(DuplicateType):
        rename_type(factory, other["id"], "סלט")
    for bad in ["", "   ", None, 5, "x" * 61]:
        with pytest.raises(ValueError):
            create_type(factory, bad)


@pytest.fixture
def api(factory, tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path, factory))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def call(method: str, path: str, body=None):
        connection = HTTPConnection("127.0.0.1", server.server_port)
        data = None if body is None else json.dumps(body).encode()
        connection.request(method, path, data, {"Content-Type": "application/json"})
        response = connection.getresponse()
        payload = json.loads(response.read() or b"null")
        connection.close()
        return response.status, payload

    yield call
    server.shutdown()
    server.server_close()


def test_http_crud_lifecycle(api) -> None:
    assert api("GET", "/api/recipe-types") == (200, [])
    status, created = api("POST", "/api/recipe-types", {"name": "סלט"})
    assert status == 201 and created["name"] == "סלט"
    path = f"/api/recipe-types/{created['id']}"
    assert api("GET", path) == (200, created)
    assert api("PUT", path, {"name": "סלטים"}) == (200, {"id": created["id"], "name": "סלטים"})
    assert api("GET", "/api/recipe-types")[1] == [{"id": created["id"], "name": "סלטים"}]
    assert api("DELETE", path) == (200, {})
    assert api("GET", path)[0] == 404
    assert api("DELETE", path)[0] == 404


def test_http_errors(api) -> None:
    api("POST", "/api/recipe-types", {"name": "סלט"})
    assert api("POST", "/api/recipe-types", {"name": "סלט"})[0] == 409
    assert api("POST", "/api/recipe-types", {"name": ""})[0] == 400
    assert api("POST", "/api/recipe-types", {"title": "x"})[0] == 400
    assert api("PUT", "/api/recipe-types/999", {"name": "x"})[0] == 404
    assert api("DELETE", "/api/recipe-types")[0] == 405
    assert api("PUT", "/api/recipe-types", {"name": "x"})[0] == 405
