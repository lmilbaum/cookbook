"""Database persistence for recipes and their optional Instagram posts."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, contains_eager, sessionmaker

from .database import session_scope
from .models import Post, Recipe

LIZAPANELIM_HOST = "lizapanelim.com"


def _is_lizapanelim_url(url: str) -> bool:
    """A recipe link counts as hers if it has no host (a local page) or is on her domain."""

    netloc = urlsplit(url).netloc.lower()
    return not netloc or netloc.removeprefix("www.") == LIZAPANELIM_HOST


def classify_source(recipe: Recipe) -> str:
    """A recipe is hers if she posted it on Instagram, regardless of an external recipe link.

    Only a recipe with no Instagram post at all falls back to the recipe
    link's own domain (e.g. a hand-curated recipe from another site).
    """

    if recipe.post is not None:
        return "lizapanelim"
    url = recipe.recipe_url.strip()
    if not url or _is_lizapanelim_url(url):
        return "lizapanelim"
    return "unknown"


def load_recipes(factory: sessionmaker[Session], reverse: bool) -> list[Recipe]:
    """Return all visible recipes in the configured report ordering."""

    ordering = Recipe.timestamp_utc.asc() if reverse else Recipe.timestamp_utc.desc()
    with factory() as session:
        return (
            session.scalars(
                select(Recipe)
                .outerjoin(Recipe.post)
                .options(contains_eager(Recipe.post))
                .where(or_(Recipe.post == None, Post.is_recipe.is_(True)))
                .order_by(ordering)
            )
            .unique()
            .all()
        )


def insert_missing_recipes(
    factory: sessionmaker[Session], recipes: Iterable[Recipe], titles: dict[str, str] | None = None
) -> int:
    """Insert new recipes, with any attached post, without replacing existing rows."""

    inserted = 0
    with session_scope(factory) as session:
        for recipe_id, title in (titles or {}).items():
            recipe = session.get(Recipe, recipe_id)
            if recipe is not None and not recipe.title.strip() and title.strip():
                recipe.title = title.strip()
        for recipe in recipes:
            if session.get(Recipe, recipe.id) is not None:
                continue
            recipe.source = classify_source(recipe)
            session.add(recipe)
            inserted += 1
    return inserted


def mark_not_recipe(factory: sessionmaker[Session], shortcode: str) -> bool:
    """Delete a post's recipe, keeping the post so the importer never re-fetches it."""

    with session_scope(factory) as session:
        post = session.get(Post, shortcode)
        if post is None:
            return False
        post.is_recipe = False
        recipe = session.get(Recipe, shortcode)
        if recipe is not None:
            session.delete(recipe)
    return True
