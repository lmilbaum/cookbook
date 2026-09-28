"""Import exported browser recipe state without replacing database edits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from .database import create_session_factory, session_scope
from .post_repository import create_manual_recipe
from .recipe_state_repository import RecipeStateConflict, save_recipe_state, valid_state


def main() -> None:
    """Initialize recipe state from a local-storage JSON export or backup."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    args = parser.parse_args()
    load_dotenv()
    try:
        state = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        parser.error("Unable to read recipe-state JSON; no data imported.")
    if not valid_state(state):
        parser.error("Invalid recipe state; no data imported.")

    factory = create_session_factory()

    # Migrate custom recipes from state.custom to database and state.overrides
    custom = state.get("custom", [])
    if custom:
        from .models import Recipe
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

    try:
        save_recipe_state(factory, state, revision=0)
    except RecipeStateConflict:
        parser.error("Recipe state is already initialized; no data imported.")
    except (SQLAlchemyError, RuntimeError):
        parser.error("Unable to import recipe state; check database configuration and migrations.")
    print("Imported recipe state. Source file retained.")


if __name__ == "__main__":
    main()
