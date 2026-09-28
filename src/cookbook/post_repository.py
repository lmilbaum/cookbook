"""Database persistence for recipes and their optional Instagram posts."""

from __future__ import annotations

import secrets
import time
from collections.abc import Iterable
from urllib.parse import urlsplit

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, contains_eager, sessionmaker

from .database import session_scope
from .models import Post, Recipe, RecipeMadeDate

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
            recipe.added_via = "instagram" if recipe.post else "manual"
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


def create_manual_recipe(title: str) -> Recipe:
    """Create a new manually added recipe and return it (unsaved)."""
    recipe_id = f"custom-{int(time.time() * 1000)}-{secrets.token_hex(8)}"
    return Recipe(
        id=recipe_id,
        image_url="",
        caption="",
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        title=title,
        recipe_url="",
        recipe_name="",
        source="unknown",
        source_name="",
        added_via="manual",
    )


def delete_manual_recipe(factory: sessionmaker[Session], recipe_id: str) -> bool:
    """Delete a manual recipe. Returns True if it existed and was deleted."""
    with session_scope(factory) as session:
        recipe = session.get(Recipe, recipe_id)
        if recipe is None or recipe.added_via != "manual":
            return False
        session.delete(recipe)
        return True


def replace_manual_with_import(factory: sessionmaker[Session], old_id: str, new_recipe_id: str) -> None:
    """Move made-dates to an import, then delete the replaced manual recipe."""
    from .made_date_repository import move_made_dates

    with session_scope(factory) as session:
        move_made_dates(session, old_id, new_recipe_id)
        recipe = session.get(Recipe, old_id)
        if recipe is not None:
            session.delete(recipe)
