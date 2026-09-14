"""Tests for the safe file-store-to-database import."""

from __future__ import annotations

import json
from dataclasses import asdict

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from cookbook.database import Base
from cookbook.models import Post, PostItem
from cookbook.post_store_import import import_post_store


def _post(shortcode: str) -> PostItem:
    return PostItem(
        shortcode=shortcode,
        url="https://example.com/post",
        image_url="https://example.com/image.jpg",
        caption="A recipe",
        timestamp_utc="2026-09-10T12:00:00+00:00",
        likes=12,
        comments=3,
        typename="GraphImage",
        is_video=False,
        title="Cake",
        recipe_url="https://example.com/recipe",
        recipe_urls=["https://example.com/recipe"],
        recipe_names=["Cake"],
    )


def test_import_post_store_inserts_each_file_once(tmp_path) -> None:
    store = tmp_path / "posts_items"
    store.mkdir()
    item = _post("cake")
    (store / "cake.json").write_text(json.dumps(asdict(item)), encoding="utf-8")
    factory = sessionmaker(bind=create_engine("sqlite://"), expire_on_commit=False)
    Base.metadata.create_all(factory.kw["bind"])

    assert import_post_store(store, factory) == 1
    assert import_post_store(store, factory) == 0

    with factory() as session:
        imported = session.scalar(select(Post).where(Post.shortcode == "cake"))
        assert imported is not None
        assert imported.title == "Cake"
        assert imported.recipe_urls == ["https://example.com/recipe"]


def test_import_post_store_does_not_overwrite_an_existing_row(tmp_path) -> None:
    store = tmp_path / "posts_items"
    store.mkdir()
    item = _post("cake")
    (store / "cake.json").write_text(json.dumps(asdict(item)), encoding="utf-8")
    factory = sessionmaker(bind=create_engine("sqlite://"), expire_on_commit=False)
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        session.add(Post(shortcode="cake", url="", image_url="", caption="", timestamp_utc="", likes=0, comments=0, typename="", is_video=False, title="Database title", recipe_url="", recipe_urls=[], recipe_names=[]))
        session.commit()

    assert import_post_store(store, factory) == 0
    with factory() as session:
        assert session.get(Post, "cake").title == "Database title"


def test_legacy_titles_fill_blanks_without_overwriting_edits(tmp_path):
    from cookbook.post_repository import insert_missing_posts
    store = tmp_path / "items"
    store.mkdir()
    titles = tmp_path / "titles.json"
    original = json.dumps({"blank": "Legacy title", "edited": "Old title", "new": "New title"})
    titles.write_text(original)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    blank, edited = _post("blank"), _post("edited")
    blank.title = ""
    edited.title = "Database edit"
    insert_missing_posts(factory, [blank, edited])
    (store / "new.json").write_text(json.dumps(asdict(_post("new"))))
    assert import_post_store(store, factory, titles) == 1
    assert import_post_store(store, factory, titles) == 0
    with factory() as session:
        assert session.get(Post, "blank").title == "Legacy title"
        assert session.get(Post, "edited").title == "Database edit"
        assert session.get(Post, "new").title == "New title"
    assert titles.read_text() == original
    engine.dispose()
