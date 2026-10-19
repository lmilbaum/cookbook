"""Test recipe thumbs up/down ratings."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from cookbook import server
from cookbook.database import Base, session_scope
from cookbook.models import Recipe
from cookbook.post_repository import replace_manual_with_import
from cookbook.rating_repository import all_ratings, get_rating, parse_rating, set_rating


def _recipe(recipe_id: str, added_via: str = "manual") -> Recipe:
    return Recipe(
        id=recipe_id,
        image_url="",
        caption="",
        timestamp_utc="2026-09-01T00:00:00Z",
        title=recipe_id,
        recipe_url="",
        recipe_name="",
        source="unknown",
        source_name="",
        added_via=added_via,
    )


@pytest.fixture
def factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite://")

    # Enable foreign key constraints on every connection
    def _enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    event.listen(engine, "connect", _enable_fk)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_scope(session_factory) as session:
        session.add(_recipe("r1"))
        session.add(_recipe("r2"))
    return session_factory


def _request(factory, tmp_path: Path, method: str, path: str, body: object = None,
             content_type: str = "application/json") -> tuple[int, dict]:
    handler = object.__new__(server.make_handler(tmp_path, factory))
    handler.path = path
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))
    raw = b"" if body is None else body if isinstance(body, bytes) else json.dumps(body).encode()
    handler.headers = {"Content-Type": content_type, "Content-Length": str(len(raw))}
    handler.rfile = io.BytesIO(raw)
    getattr(handler, f"do_{method}")()
    return responses.pop()


def test_parse_rating_accepts_up_down_and_none():
    """parse_rating accepts 'up', 'down' and None (clear)."""
    assert parse_rating("up") == "up"
    assert parse_rating("down") == "down"
    assert parse_rating(None) is None


@pytest.mark.parametrize("value", ["sideways", "", True, 1])
def test_parse_rating_rejects_other_values(value):
    """parse_rating rejects anything that is not up, down or None."""
    with pytest.raises(ValueError, match="Invalid rating"):
        parse_rating(value)


def test_set_and_get_rating(factory):
    """set_rating stores up, switches to down, and None removes the row."""
    set_rating(factory, "r1", "up")
    assert get_rating(factory, "r1") == "up"

    set_rating(factory, "r1", "down")
    assert get_rating(factory, "r1") == "down"

    set_rating(factory, "r1", None)
    assert get_rating(factory, "r1") is None
    assert all_ratings(factory) == {}


def test_all_ratings_returns_only_rated_recipes(factory):
    """all_ratings maps only the recipes that have a rating."""
    set_rating(factory, "r1", "up")
    set_rating(factory, "r2", "down")
    set_rating(factory, "r2", None)

    assert all_ratings(factory) == {"r1": "up"}


def test_deleting_recipe_cascades_to_rating(factory):
    """Deleting a recipe removes its rating."""
    set_rating(factory, "r1", "up")

    with session_scope(factory) as session:
        session.delete(session.get(Recipe, "r1"))

    assert all_ratings(factory) == {}


def test_replace_manual_with_import_moves_rating(factory):
    """Replacing a manual recipe moves its rating to the imported recipe."""
    set_rating(factory, "r1", "down")

    replace_manual_with_import(factory, "r1", "r2")

    assert all_ratings(factory) == {"r2": "down"}
    with session_scope(factory) as session:
        assert session.get(Recipe, "r1") is None


def test_replace_manual_with_import_keeps_target_rating(factory):
    """If the imported recipe already has a rating, it wins over the replaced recipe's."""
    set_rating(factory, "r1", "down")
    set_rating(factory, "r2", "up")

    replace_manual_with_import(factory, "r1", "r2")

    assert all_ratings(factory) == {"r2": "up"}


def test_put_rating_then_get_lists_it(factory, tmp_path):
    """PUT sets a rating and GET /api/recipe-ratings lists it."""
    assert _request(factory, tmp_path, "PUT", "/api/recipes/r1/rating", {"rating": "up"}) == (
        200, {"rating": "up"},
    )
    assert _request(factory, tmp_path, "GET", "/api/recipe-ratings") == (
        200, {"ratings": {"r1": "up"}},
    )


def test_put_null_clears_rating(factory, tmp_path):
    """PUT with a null rating clears the stored rating."""
    set_rating(factory, "r1", "up")

    assert _request(factory, tmp_path, "PUT", "/api/recipes/r1/rating", {"rating": None}) == (
        200, {"rating": None},
    )
    assert all_ratings(factory) == {}


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        ({"rating": "meh"}, "application/json"),
        ({"rating": "up", "extra": 1}, "application/json"),
        ({}, "application/json"),
        ({"rating": "up"}, "text/plain"),
        (b"", "application/json"),
        (b"not json", "application/json"),
    ],
)
def test_put_rating_rejects_invalid_requests(factory, tmp_path, body, content_type):
    """PUT returns 400 for bad values, extra keys, or a non-JSON body or content type."""
    status, payload = _request(factory, tmp_path, "PUT", "/api/recipes/r1/rating", body, content_type)

    assert status == 400
    assert "error" in payload
    assert all_ratings(factory) == {}


def test_put_rating_unknown_recipe_returns_404(factory, tmp_path):
    """PUT on a recipe that does not exist returns 404."""
    status, _ = _request(factory, tmp_path, "PUT", "/api/recipes/missing/rating", {"rating": "up"})

    assert status == 404


def test_rating_routes_return_503_when_database_fails(tmp_path):
    """Database errors on the rating routes return 503."""
    def broken_factory():
        raise SQLAlchemyError("database is unavailable")

    status, payload = _request(broken_factory, tmp_path, "PUT", "/api/recipes/r1/rating", {"rating": "up"})
    assert status == 503
    assert "error" in payload

    status, payload = _request(broken_factory, tmp_path, "GET", "/api/recipe-ratings")
    assert status == 503
    assert "error" in payload
