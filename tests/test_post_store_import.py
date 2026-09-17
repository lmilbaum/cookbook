"""Tests for the safe file-store-to-database import."""

from __future__ import annotations

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from cookbook.database import Base
from cookbook.models import Recipe
from cookbook.post_store_import import import_post_store


def _flat_post_payload(shortcode: str) -> dict[str, object]:
    """Build a legacy flat per-post JSON payload, the on-disk store's format."""

    return {
        "shortcode": shortcode,
        "url": "https://example.com/post",
        "image_url": "https://example.com/image.jpg",
        "caption": "A recipe",
        "timestamp_utc": "2026-09-10T12:00:00+00:00",
        "likes": 12,
        "comments": 3,
        "typename": "GraphImage",
        "is_video": False,
        "title": "Cake",
        "recipe_url": "https://example.com/recipe",
        "recipe_urls": ["https://example.com/recipe"],
        "recipe_names": ["Cake"],
    }


def test_import_post_store_inserts_each_file_once(tmp_path) -> None:
    store = tmp_path / "posts_items"
    store.mkdir()
    (store / "cake.json").write_text(json.dumps(_flat_post_payload("cake")), encoding="utf-8")
    factory = sessionmaker(bind=create_engine("sqlite://"), expire_on_commit=False)
    Base.metadata.create_all(factory.kw["bind"])

    assert import_post_store(store, factory) == 1
    assert import_post_store(store, factory) == 0

    with factory() as session:
        imported = session.scalar(select(Recipe).where(Recipe.id == "cake"))
        assert imported is not None
        assert imported.title == "Cake"
        assert imported.recipe_url == "https://example.com/recipe"


def test_import_post_store_does_not_overwrite_an_existing_row(tmp_path) -> None:
    store = tmp_path / "posts_items"
    store.mkdir()
    (store / "cake.json").write_text(json.dumps(_flat_post_payload("cake")), encoding="utf-8")
    factory = sessionmaker(bind=create_engine("sqlite://"), expire_on_commit=False)
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        session.add(Recipe(id="cake", image_url="", caption="", timestamp_utc="", title="Database title"))
        session.commit()

    assert import_post_store(store, factory) == 0
    with factory() as session:
        assert session.get(Recipe, "cake").title == "Database title"


def test_legacy_titles_fill_blanks_without_overwriting_edits(tmp_path):
    from cookbook.post_repository import insert_missing_recipes
    store = tmp_path / "items"
    store.mkdir()
    titles = tmp_path / "titles.json"
    original = json.dumps({"blank": "Legacy title", "edited": "Old title", "new": "New title"})
    titles.write_text(original)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    blank = Recipe(id="blank", image_url="", caption="", timestamp_utc="2026-09-10T12:00:00+00:00", title="")
    edited = Recipe(id="edited", image_url="", caption="", timestamp_utc="2026-09-10T12:00:00+00:00", title="Database edit")
    insert_missing_recipes(factory, [blank, edited])
    (store / "new.json").write_text(json.dumps(_flat_post_payload("new")))
    assert import_post_store(store, factory, titles) == 1
    assert import_post_store(store, factory, titles) == 0
    with factory() as session:
        assert session.get(Recipe, "blank").title == "Legacy title"
        assert session.get(Recipe, "edited").title == "Database edit"
        assert session.get(Recipe, "new").title == "New title"
    assert titles.read_text() == original
    engine.dispose()
