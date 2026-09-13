"""Persist browser-authored recipe edits with optimistic concurrency control."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import RecipeState


class RecipeStateConflict(ValueError):
    """A client attempted to replace a newer version of the cookbook."""


def valid_state(value: object) -> bool:
    """Validate the existing browser format before storing it."""

    if not isinstance(value, dict) or set(value) - {"overrides", "custom", "order"}:
        return False
    overrides, custom = value.get("overrides"), value.get("custom")
    if not isinstance(overrides, dict) or not isinstance(custom, list):
        return False
    strings = {"id", "title", "recipeUrl", "recipeName", "sourceUrl", "imageUrl",
               "instructions", "prerequisiteId", "notes", "timestamp"}
    arrays = {"recipeUrls", "recipeNames"}
    for recipe in [*overrides.values(), *custom]:
        if not isinstance(recipe, dict) or set(recipe) - strings - arrays - {"ingredients"}:
            return False
        if any(not isinstance(recipe[key], str) for key in strings & recipe.keys()):
            return False
        for key in arrays & recipe.keys():
            if not isinstance(recipe[key], list) or not all(isinstance(x, str) for x in recipe[key]):
                return False
        if "ingredients" in recipe:
            if not isinstance(recipe["ingredients"], list):
                return False
            for ingredient in recipe["ingredients"]:
                if (not isinstance(ingredient, dict)
                    or set(ingredient) - {"name", "varieties", "amount"}
                    or not all(isinstance(x, str) for x in ingredient.values())):
                    return False
    ids = [recipe.get("id") for recipe in custom]
    if any(not isinstance(id_, str) or not id_ or id_ in overrides for id_ in ids):
        return False
    if len(set(ids)) != len(ids):
        return False
    if any("id" in recipe and recipe["id"] != key for key, recipe in overrides.items()):
        return False
    return "order" not in value or (
        isinstance(value["order"], list) and all(isinstance(x, str) for x in value["order"])
    )


def load_recipe_state(factory: sessionmaker[Session]) -> dict[str, Any]:
    with factory() as session:
        row = session.get(RecipeState, 1)
        if row is None:
            return {"revision": 0, "state": {"overrides": {}, "custom": []}}
        return {"revision": row.revision, "state": row.payload}


def save_recipe_state(factory: sessionmaker[Session], state: dict[str, Any], revision: int) -> int:
    """Replace a matching revision atomically, including the first import."""

    if not valid_state(state) or type(revision) is not int or revision < 0:
        raise ValueError("Invalid recipe state")
    with session_scope(factory) as session:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("LOCK TABLE recipe_state IN EXCLUSIVE MODE"))
        row = session.get(RecipeState, 1)
        if revision != (row.revision if row else 0):
            raise RecipeStateConflict("Recipe state changed; reload before saving.")
        if row is None:
            session.add(RecipeState(id=1, revision=1, payload=state))
        else:
            row.revision += 1
            row.payload = state
    return revision + 1
