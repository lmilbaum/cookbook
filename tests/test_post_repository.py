"""Tests for database-backed post persistence."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cookbook.database import Base
from cookbook.models import PostItem
from cookbook.post_repository import insert_missing_posts, load_posts, mark_not_recipe


def _post(shortcode: str, timestamp: str) -> PostItem:
    return PostItem(
        shortcode=shortcode,
        url="https://example.com/post",
        image_url="",
        caption="",
        timestamp_utc=timestamp,
        likes=0,
        comments=0,
        typename="GraphImage",
        is_video=False,
    )


def test_posts_are_inserted_once_and_loaded_in_report_order() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    oldest = _post("oldest", "2026-01-01T00:00:00+00:00")
    newest = _post("newest", "2026-01-02T00:00:00+00:00")

    assert insert_missing_posts(factory, [newest, oldest]) == 2
    assert insert_missing_posts(factory, [newest]) == 0
    assert [post.shortcode for post in load_posts(factory, reverse=True)] == [
        "oldest",
        "newest",
    ]
    assert [post.shortcode for post in load_posts(factory, reverse=False)] == [
        "newest",
        "oldest",
    ]


def test_mark_not_recipe_excludes_a_post_from_reports() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    item = _post("not-a-recipe", "2026-01-01T00:00:00+00:00")
    insert_missing_posts(factory, [item])

    assert mark_not_recipe(factory, item.shortcode)
    assert load_posts(factory, reverse=False) == []
