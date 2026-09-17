"""Tests for database-backed recipe/post persistence."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cookbook.database import Base
from cookbook.models import Post, Recipe
from cookbook.post_repository import (
    classify_source,
    insert_missing_recipes,
    load_recipes,
    mark_not_recipe,
)


def _recipe(shortcode: str, timestamp: str, **overrides: object) -> Recipe:
    values: dict[str, object] = {
        "id": shortcode,
        "image_url": "",
        "caption": "",
        "timestamp_utc": timestamp,
    }
    values.update(overrides)
    recipe = Recipe(**values)  # type: ignore[arg-type]
    recipe.post = Post(shortcode=shortcode, url="https://example.com/post", typename="GraphImage", is_video=False)
    return recipe


def _bare_recipe(shortcode: str, **overrides: object) -> Recipe:
    """A recipe with no attached Instagram post."""

    values: dict[str, object] = {
        "id": shortcode,
        "image_url": "",
        "caption": "",
        "timestamp_utc": "2026-01-01T00:00:00+00:00",
    }
    values.update(overrides)
    return Recipe(**values)  # type: ignore[arg-type]


def test_classify_source_prefers_instagram_origin_over_recipe_link_domain() -> None:
    # A post she published herself is always hers, even when the recipe it
    # links to lives on someone else's site (e.g. she reposted a find).
    assert classify_source(_recipe("with-post", "t", recipe_url="https://www.marthastewart.com/x")) == "lizapanelim"

    # With no Instagram post at all, fall back to the recipe link's own domain.
    assert classify_source(_bare_recipe("no-post-blank")) == "lizapanelim"
    assert classify_source(_bare_recipe("no-post-local", recipe_url="recipes/apple_cake.html")) == "lizapanelim"
    assert classify_source(_bare_recipe("no-post-liza", recipe_url="https://lizapanelim.com/x/")) == "lizapanelim"
    assert classify_source(_bare_recipe("no-post-www-liza", recipe_url="https://www.lizapanelim.com/x/")) == "lizapanelim"
    assert classify_source(_bare_recipe("no-post-other", recipe_url="https://www.marthastewart.com/x")) == "other"


def test_inserted_recipes_are_classified_by_instagram_origin_first() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    posted_elsewhere = _recipe(
        "posted-elsewhere", "2026-01-01T00:00:00+00:00", recipe_url="https://www.marthastewart.com/x"
    )
    never_posted = _bare_recipe("never-posted", recipe_url="https://www.marthastewart.com/x")

    insert_missing_recipes(factory, [posted_elsewhere, never_posted])

    recipes_by_id = {recipe.id: recipe for recipe in load_recipes(factory, reverse=True)}
    assert recipes_by_id["posted-elsewhere"].source == "lizapanelim"
    assert recipes_by_id["never-posted"].source == "other"


def test_recipes_are_inserted_once_and_loaded_in_report_order() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    oldest = _recipe("oldest", "2026-01-01T00:00:00+00:00")
    newest = _recipe("newest", "2026-01-02T00:00:00+00:00")

    assert insert_missing_recipes(factory, [newest, oldest]) == 2
    assert insert_missing_recipes(factory, [newest]) == 0
    assert [recipe.id for recipe in load_recipes(factory, reverse=True)] == [
        "oldest",
        "newest",
    ]
    assert [recipe.id for recipe in load_recipes(factory, reverse=False)] == [
        "newest",
        "oldest",
    ]


def test_recipe_with_no_post_is_always_visible() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    hand_curated = Recipe(id="classic-applesauce", image_url="", caption="", timestamp_utc="2026-01-01T00:00:00+00:00")

    insert_missing_recipes(factory, [hand_curated])

    assert [recipe.id for recipe in load_recipes(factory, reverse=False)] == ["classic-applesauce"]


def test_mark_not_recipe_excludes_a_post_from_reports_without_touching_the_recipe() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    item = _recipe("not-a-recipe", "2026-01-01T00:00:00+00:00")
    insert_missing_recipes(factory, [item])

    assert mark_not_recipe(factory, item.post.shortcode)
    assert load_recipes(factory, reverse=False) == []
