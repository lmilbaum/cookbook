"""Persist browser-authored recipe edits with optimistic concurrency control."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import Recipe, RecipeState


class RecipeStateConflict(ValueError):
    """A client attempted to replace a newer version of the cookbook."""


def valid_state(value: object) -> bool:
    """Validate the existing browser format before storing it."""

    if not isinstance(value, dict) or set(value) - {"overrides", "custom", "order", "types"}:
        return False
    overrides, custom = value.get("overrides"), value.get("custom")
    if not isinstance(overrides, dict) or not isinstance(custom, list):
        return False
    strings = {"id", "title", "recipeUrl", "recipeName", "sourceUrl", "imageUrl",
               "instructions", "type", "source", "sourceName", "prerequisiteId", "notes", "timestamp"}
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
    types = value.get("types", [])
    if not isinstance(types, list) or not all(isinstance(x, str) and x.strip() for x in types):
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
            result = {"revision": 0, "state": {"overrides": {}, "custom": []}}
        else:
            result = {"revision": row.revision, "state": dict(row.payload)}

        # Self-heal state.order:
        # 1. Remove IDs for recipes that no longer exist in the DB (e.g. a custom recipe
        #    that was replaced by an Instagram import deletes its row, but the browser may
        #    have saved the stale ID before reloading — causing createCard(undefined) crash).
        # 2. Append custom recipe IDs that exist in the DB but are absent from state.order
        #    (recovers from POST /api/recipes race where the 201 never reached the browser).
        all_ids = set(session.scalars(select(Recipe.id)))
        order: list[str] = list(result["state"].get("order", []))
        order = [rid for rid in order if rid in all_ids]
        custom_ids = list(
            session.scalars(select(Recipe.id).where(Recipe.added_via == "manual"))
        )
        order_set = set(order)
        missing = [rid for rid in custom_ids if rid not in order_set]
        if missing or len(order) != len(result["state"].get("order", [])):
            result["state"] = {**result["state"], "order": order + missing}

        return result


def save_recipe_state(factory: sessionmaker[Session], state: dict[str, Any], revision: int) -> int:
    """Replace a matching revision atomically, including the first import."""

    if not valid_state(state) or type(revision) is not int or revision < 0:
        raise ValueError("Invalid recipe state")

    # Migration shim: promote old-format saves with state.custom to new format
    custom = state.get("custom", [])
    if custom:
        from .post_repository import create_manual_recipe
        with session_scope(factory) as session:
            for custom_recipe in custom:
                recipe_id = custom_recipe.get("id")
                if not recipe_id:
                    continue
                # Only insert if the recipe doesn't already exist
                if session.get(Recipe, recipe_id) is None:
                    # Create and insert the custom recipe
                    new_recipe = create_manual_recipe(custom_recipe.get("title", ""))
                    new_recipe.id = recipe_id
                    new_recipe.image_url = custom_recipe.get("imageUrl", "")
                    new_recipe.source = custom_recipe.get("source", "unknown")
                    new_recipe.source_name = custom_recipe.get("sourceName", "")
                    session.add(new_recipe)
                # Move to overrides
                state.setdefault("overrides", {})[recipe_id] = custom_recipe
        state["custom"] = []

    with session_scope(factory) as session:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("LOCK TABLE recipe_states IN EXCLUSIVE MODE"))
        row = session.get(RecipeState, 1)
        if revision != (row.revision if row else 0):
            raise RecipeStateConflict("Recipe state changed; reload before saving.")
        if row is None:
            session.add(RecipeState(id=1, revision=1, payload=state))
        else:
            row.revision += 1
            row.payload = state
    return revision + 1


def fill_recipe_override(
    factory: sessionmaker[Session],
    recipe_id: str,
    fields: dict[str, Any],
    attempts: int = 3,
) -> tuple[int, dict[str, Any]] | None:
    """
    Fill a recipe override with parsed caption fields, retrying on conflicts.

    Returns (new_revision, written_fields) on success, or None if revision == 0 or all retries exhausted.

    Only writes non-empty fields:
    - String: blank if missing, empty, all-whitespace, or matches stale title wrapper pattern
    - List: blank if missing or empty
    """
    import re

    stale_title_pattern = re.compile(r"[\d.,]+[KkMm]?\s*likes?")

    for _ in range(attempts):
        current = load_recipe_state(factory)
        if current["revision"] == 0:
            return None

        state = {
            "overrides": dict(current["state"].get("overrides", {})),
            "custom": list(current["state"].get("custom", [])),
        }
        if "order" in current["state"]:
            state["order"] = list(current["state"]["order"])
        if "types" in current["state"]:
            state["types"] = list(current["state"]["types"])

        existing = state["overrides"].get(recipe_id, {})
        written: dict[str, Any] = {}

        for key, value in fields.items():
            existing_value = existing.get(key)
            if isinstance(value, list):
                # Only write non-empty lists when existing value is blank
                if not existing_value:
                    written[key] = value
            else:
                # Only write non-blank, non-stale strings when existing value is blank
                ev = str(existing_value or "").strip()
                if not ev or stale_title_pattern.search(ev):
                    # Existing is blank or stale; check if new value is non-blank and non-stale
                    is_blank = not value or not value.strip()
                    is_stale = stale_title_pattern.search(value) if value else False
                    if not is_blank and not is_stale:
                        written[key] = value

        if not written:
            return None

        state["overrides"][recipe_id] = {**existing, "id": recipe_id, **written}

        try:
            new_rev = save_recipe_state(factory, state, current["revision"])
            return new_rev, written
        except RecipeStateConflict:
            continue

    return None


def image_url_overrides(state: dict[str, Any]) -> dict[str, str]:
    """Return override image URLs that point at downloadable http(s) addresses."""

    result: dict[str, str] = {}
    for recipe_id, override in state.get("overrides", {}).items():
        if not isinstance(override, dict):
            continue
        url = str(override.get("imageUrl", "")).strip()
        if url.startswith(("http://", "https://")):
            result[recipe_id] = url
    return result


def override_image_urls(factory: sessionmaker[Session]) -> dict[str, str]:
    """Return the downloadable override image URLs saved in the database."""

    with factory() as session:
        row = session.get(RecipeState, 1)
        if row is None:
            return {}
        return image_url_overrides(row.payload)
