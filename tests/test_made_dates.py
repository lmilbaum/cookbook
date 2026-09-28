"""Test recipe made-on dates."""

from __future__ import annotations

import io
import json
from datetime import date

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from cookbook import server
from cookbook.database import Base, session_scope
from cookbook.made_date_repository import (
    add_made_date,
    list_made_dates,
    parse_made_on,
    remove_made_date,
    move_made_dates,
)
from cookbook.models import Recipe


def test_parse_made_on_valid():
    """parse_made_on accepts valid ISO dates."""
    assert parse_made_on("2026-09-27") == date(2026, 9, 27)


def test_parse_made_on_rejects_compact():
    """parse_made_on rejects compact form like 20260927."""
    with pytest.raises(ValueError, match="Invalid date"):
        parse_made_on("20260927")


def test_parse_made_on_rejects_short_month():
    """parse_made_on rejects non-zero-padded month."""
    with pytest.raises(ValueError, match="Invalid date"):
        parse_made_on("2026-9-01")


def test_parse_made_on_rejects_invalid_date():
    """parse_made_on rejects invalid dates like 2026-02-30."""
    with pytest.raises(ValueError):
        parse_made_on("2026-02-30")


def test_parse_made_on_rejects_non_string():
    """parse_made_on rejects non-string input."""
    with pytest.raises(ValueError, match="Invalid date"):
        parse_made_on(20260927)


def test_add_made_date(initialized_db):
    """add_made_date adds a date and returns True on first add, False on duplicate."""
    factory, recipe_id = initialized_db
    made_on = date(2026, 9, 27)

    # First add should succeed
    assert add_made_date(factory, recipe_id, made_on) is True

    # Duplicate should fail
    assert add_made_date(factory, recipe_id, made_on) is False


def test_list_made_dates_newest_first(initialized_db):
    """list_made_dates returns dates newest first."""
    factory, recipe_id = initialized_db

    add_made_date(factory, recipe_id, date(2026, 9, 1))
    add_made_date(factory, recipe_id, date(2026, 9, 20))
    add_made_date(factory, recipe_id, date(2026, 9, 10))

    dates = list_made_dates(factory, recipe_id)
    assert dates == ["2026-09-20", "2026-09-10", "2026-09-01"]


def test_remove_made_date(initialized_db):
    """remove_made_date removes a date and returns True if it existed."""
    factory, recipe_id = initialized_db
    made_on = date(2026, 9, 27)

    add_made_date(factory, recipe_id, made_on)

    # First remove should succeed
    assert remove_made_date(factory, recipe_id, made_on) is True

    # Second remove should fail
    assert remove_made_date(factory, recipe_id, made_on) is False


def test_move_made_dates(initialized_db):
    """move_made_dates moves all dates from one recipe to another."""
    factory, recipe_id_1 = initialized_db

    # Create second recipe
    with session_scope(factory) as session:
        recipe_id_2 = "recipe-2"
        recipe_2 = Recipe(
            id=recipe_id_2,
            image_url="",
            caption="",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Recipe 2",
            recipe_url="",
            recipe_name="",
            source="unknown",
            source_name="",
            added_via="manual",
        )
        session.add(recipe_2)

    # Add dates to first recipe
    add_made_date(factory, recipe_id_1, date(2026, 9, 1))
    add_made_date(factory, recipe_id_1, date(2026, 9, 20))

    # Move dates
    with session_scope(factory) as session:
        move_made_dates(session, recipe_id_1, recipe_id_2)

    # Check first recipe has no dates
    assert list_made_dates(factory, recipe_id_1) == []

    # Check second recipe has dates
    assert list_made_dates(factory, recipe_id_2) == ["2026-09-20", "2026-09-01"]


def test_move_made_dates_handles_conflict(initialized_db):
    """move_made_dates drops source date on conflict."""
    factory, recipe_id_1 = initialized_db

    # Create second recipe
    with session_scope(factory) as session:
        recipe_id_2 = "recipe-2"
        recipe_2 = Recipe(
            id=recipe_id_2,
            image_url="",
            caption="",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Recipe 2",
            recipe_url="",
            recipe_name="",
            source="unknown",
            source_name="",
            added_via="manual",
        )
        session.add(recipe_2)

    # Add same date to both recipes
    date_val = date(2026, 9, 15)
    add_made_date(factory, recipe_id_1, date_val)
    add_made_date(factory, recipe_id_2, date_val)

    # Move dates (should handle conflict)
    with session_scope(factory) as session:
        move_made_dates(session, recipe_id_1, recipe_id_2)

    # Check first recipe has no dates
    assert list_made_dates(factory, recipe_id_1) == []

    # Check second recipe still has only one instance of the date
    assert list_made_dates(factory, recipe_id_2) == ["2026-09-15"]


def test_made_dates_cascade_delete(initialized_db):
    """Deleting a recipe cascades to made-dates (with foreign keys enabled)."""
    factory, recipe_id = initialized_db

    add_made_date(factory, recipe_id, date(2026, 9, 27))

    # Delete the recipe (foreign keys already enabled by fixture)
    with session_scope(factory) as session:
        recipe = session.get(Recipe, recipe_id)
        session.delete(recipe)

    # Check that made-dates were cascaded deleted
    dates = list_made_dates(factory, recipe_id)
    assert dates == []


def test_post_api_recipes_creates_custom_recipe(tmp_path):
    """POST /api/recipes creates a manual recipe with added_via='manual' and returns 201."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    body = json.dumps({"title": "My Custom Recipe"}).encode()
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    handler.rfile = io.BytesIO(body)

    handler.do_POST()
    status, payload = responses.pop()

    assert status == 201
    assert payload["added_via"] == "manual"
    assert "id" in payload


def test_post_api_recipes_accepts_extra_fields(tmp_path):
    """POST /api/recipes ignores unknown keys in the body."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    body = json.dumps({"title": "My Custom Recipe", "extra": "field"}).encode()
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    handler.rfile = io.BytesIO(body)

    handler.do_POST()
    status, payload = responses.pop()

    # Should still succeed - the server accepts extra fields
    assert status == 201


def test_post_api_recipes_rejects_empty_title(tmp_path):
    """POST /api/recipes rejects empty title."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    body = json.dumps({"title": "   "}).encode()
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    handler.rfile = io.BytesIO(body)

    handler.do_POST()
    status, payload = responses.pop()

    assert status == 400
    assert "error" in payload


def test_delete_api_recipes_deletes_custom_recipe(tmp_path):
    """DELETE /api/recipes/<id> deletes a custom recipe and returns 200."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Create a custom recipe
    with session_scope(factory) as session:
        recipe = Recipe(
            id="custom-test-123",
            image_url="",
            caption="",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Custom Recipe",
            recipe_url="",
            recipe_name="",
            source="unknown",
            source_name="",
            added_via="manual",
        )
        session.add(recipe)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes/custom-test-123"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    handler.do_DELETE()
    status, payload = responses.pop()

    assert status == 200
    assert payload == {}

    # Verify recipe was deleted
    with factory() as session:
        recipe = session.get(Recipe, "custom-test-123")
        assert recipe is None


def test_delete_api_recipes_rejects_non_custom_recipe(tmp_path):
    """DELETE /api/recipes/<id> returns 404 for non-custom (imported) recipes."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Create an imported recipe
    with session_scope(factory) as session:
        recipe = Recipe(
            id="instagram-abc123",
            image_url="",
            caption="",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Instagram Recipe",
            recipe_url="",
            recipe_name="",
            source="lizapanelim",
            source_name="",
            added_via="instagram",
        )
        session.add(recipe)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes/instagram-abc123"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    handler.do_DELETE()
    status, payload = responses.pop()

    assert status == 404
    assert "error" in payload

    # Verify recipe still exists
    with factory() as session:
        recipe = session.get(Recipe, "instagram-abc123")
        assert recipe is not None


def test_delete_api_recipes_returns_404_for_unknown_id(tmp_path):
    """DELETE /api/recipes/<id> returns 404 for unknown recipe ids."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes/nonexistent-id"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    handler.do_DELETE()
    status, payload = responses.pop()

    assert status == 404
    assert "error" in payload


def test_get_api_made_dates_returns_empty_list(tmp_path):
    """GET /api/recipes/<id>/made-dates returns empty list initially."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Create a recipe
    with session_scope(factory) as session:
        recipe = Recipe(
            id="recipe-1",
            image_url="",
            caption="",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Test Recipe",
            recipe_url="",
            recipe_name="",
            source="unknown",
            source_name="",
            added_via="manual",
        )
        session.add(recipe)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes/recipe-1/made-dates"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    handler.do_GET()
    status, payload = responses.pop()

    assert status == 200
    assert payload == {"dates": []}


def test_post_api_made_dates_adds_date(tmp_path):
    """POST /api/recipes/<id>/made-dates adds a made date and returns 201."""
    engine = create_engine("sqlite://")
    def _enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    event.listen(engine, "connect", _enable_fk)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Create a recipe
    with session_scope(factory) as session:
        recipe = Recipe(
            id="recipe-1",
            image_url="",
            caption="",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Test Recipe",
            recipe_url="",
            recipe_name="",
            source="unknown",
            source_name="",
            added_via="manual",
        )
        session.add(recipe)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes/recipe-1/made-dates"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    body = json.dumps({"date": "2026-09-15"}).encode()
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    handler.rfile = io.BytesIO(body)

    handler.do_POST()
    status, payload = responses.pop()

    assert status == 201
    assert payload == {"dates": ["2026-09-15"]}


def test_post_api_made_dates_duplicate_returns_201_but_no_duplicate(tmp_path):
    """POST /api/recipes/<id>/made-dates with same date twice returns 201 but no duplicate."""
    engine = create_engine("sqlite://")
    def _enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    event.listen(engine, "connect", _enable_fk)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Create a recipe
    with session_scope(factory) as session:
        recipe = Recipe(
            id="recipe-1",
            image_url="",
            caption="",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Test Recipe",
            recipe_url="",
            recipe_name="",
            source="unknown",
            source_name="",
            added_via="manual",
        )
        session.add(recipe)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes/recipe-1/made-dates"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    # Add first date
    body = json.dumps({"date": "2026-09-15"}).encode()
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    handler.rfile = io.BytesIO(body)
    handler.do_POST()
    status1, payload1 = responses.pop()

    # Add same date again
    body = json.dumps({"date": "2026-09-15"}).encode()
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    handler.rfile = io.BytesIO(body)
    handler.do_POST()
    status2, payload2 = responses.pop()

    assert status1 == 201
    assert status2 == 201
    # Both should return the same list with just one date
    assert payload1 == {"dates": ["2026-09-15"]}
    assert payload2 == {"dates": ["2026-09-15"]}


def test_post_api_made_dates_rejects_bad_date(tmp_path):
    """POST /api/recipes/<id>/made-dates rejects invalid date format."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Create a recipe
    with session_scope(factory) as session:
        recipe = Recipe(
            id="recipe-1",
            image_url="",
            caption="",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Test Recipe",
            recipe_url="",
            recipe_name="",
            source="unknown",
            source_name="",
            added_via="manual",
        )
        session.add(recipe)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes/recipe-1/made-dates"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    body = json.dumps({"date": "2026/09/15"}).encode()
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    handler.rfile = io.BytesIO(body)

    handler.do_POST()
    status, payload = responses.pop()

    assert status == 400
    assert "error" in payload


def test_post_api_made_dates_rejects_unknown_recipe(tmp_path):
    """POST /api/recipes/<id>/made-dates returns 404 for unknown recipe."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes/nonexistent/made-dates"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    body = json.dumps({"date": "2026-09-15"}).encode()
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    handler.rfile = io.BytesIO(body)

    handler.do_POST()
    status, payload = responses.pop()

    assert status == 404
    assert "error" in payload


def test_delete_api_made_dates_removes_date(tmp_path):
    """DELETE /api/recipes/<id>/made-dates/<date> removes a date and returns 200."""
    engine = create_engine("sqlite://")
    def _enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    event.listen(engine, "connect", _enable_fk)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Create a recipe with a made date
    with session_scope(factory) as session:
        recipe = Recipe(
            id="recipe-1",
            image_url="",
            caption="",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Test Recipe",
            recipe_url="",
            recipe_name="",
            source="unknown",
            source_name="",
            added_via="manual",
        )
        session.add(recipe)

    add_made_date(factory, "recipe-1", date(2026, 9, 15))

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes/recipe-1/made-dates/2026-09-15"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    handler.do_DELETE()
    status, payload = responses.pop()

    assert status == 200
    assert payload == {"dates": []}


def test_delete_api_made_dates_returns_404_for_missing_date(tmp_path):
    """DELETE /api/recipes/<id>/made-dates/<date> returns 404 if date doesn't exist."""
    engine = create_engine("sqlite://")
    def _enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    event.listen(engine, "connect", _enable_fk)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Create a recipe
    with session_scope(factory) as session:
        recipe = Recipe(
            id="recipe-1",
            image_url="",
            caption="",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Test Recipe",
            recipe_url="",
            recipe_name="",
            source="unknown",
            source_name="",
            added_via="manual",
        )
        session.add(recipe)

    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = "/api/recipes/recipe-1/made-dates/2026-09-15"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    handler.do_DELETE()
    status, payload = responses.pop()

    assert status == 404
    assert "error" in payload


def test_made_dates_full_lifecycle(tmp_path):
    """Test the full HTTP lifecycle: GET empty → POST 201 → GET returns list → DELETE 200 → GET empty."""
    engine = create_engine("sqlite://")
    def _enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    event.listen(engine, "connect", _enable_fk)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Create a recipe
    with session_scope(factory) as session:
        recipe = Recipe(
            id="recipe-1",
            image_url="",
            caption="",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Test Recipe",
            recipe_url="",
            recipe_name="",
            source="unknown",
            source_name="",
            added_via="manual",
        )
        session.add(recipe)

    responses = []

    def make_handler():
        h = object.__new__(server.make_handler(tmp_path, factory))
        h._json_response = lambda status, payload: responses.append((status, payload))
        return h

    # GET empty
    handler = make_handler()
    handler.path = "/api/recipes/recipe-1/made-dates"
    handler.do_GET()
    assert responses.pop() == (200, {"dates": []})

    # POST date 1
    handler = make_handler()
    handler.path = "/api/recipes/recipe-1/made-dates"
    body = json.dumps({"date": "2026-09-20"}).encode()
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    handler.rfile = io.BytesIO(body)
    handler.do_POST()
    assert responses.pop() == (201, {"dates": ["2026-09-20"]})

    # POST date 2
    handler = make_handler()
    handler.path = "/api/recipes/recipe-1/made-dates"
    body = json.dumps({"date": "2026-09-10"}).encode()
    handler.headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    handler.rfile = io.BytesIO(body)
    handler.do_POST()
    assert responses.pop() == (201, {"dates": ["2026-09-20", "2026-09-10"]})

    # GET returns newest first
    handler = make_handler()
    handler.path = "/api/recipes/recipe-1/made-dates"
    handler.do_GET()
    assert responses.pop() == (200, {"dates": ["2026-09-20", "2026-09-10"]})

    # DELETE first date
    handler = make_handler()
    handler.path = "/api/recipes/recipe-1/made-dates/2026-09-20"
    handler.do_DELETE()
    assert responses.pop() == (200, {"dates": ["2026-09-10"]})

    # DELETE second date
    handler = make_handler()
    handler.path = "/api/recipes/recipe-1/made-dates/2026-09-10"
    handler.do_DELETE()
    assert responses.pop() == (200, {"dates": []})

    # DELETE non-existent date
    handler = make_handler()
    handler.path = "/api/recipes/recipe-1/made-dates/2026-09-05"
    handler.do_DELETE()
    status, payload = responses.pop()
    assert status == 404
    assert "error" in payload


@pytest.fixture
def initialized_db():
    """Create an initialized in-memory database with a recipe for testing."""
    engine = create_engine("sqlite://")

    # Enable foreign key constraints on every connection
    def _enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    event.listen(engine, "connect", _enable_fk)
    Base.metadata.create_all(engine)

    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Insert a test recipe
    with session_scope(factory) as session:
        recipe = Recipe(
            id="test-recipe-id",
            image_url="https://example.com/image.jpg",
            caption="Test caption",
            timestamp_utc="2026-09-01T00:00:00Z",
            title="Test Recipe",
            recipe_url="",
            recipe_name="",
            source="unknown",
            source_name="",
            added_via="manual",
        )
        session.add(recipe)

    yield factory, "test-recipe-id"
