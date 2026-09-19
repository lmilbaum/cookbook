"""Import file-backed recipe posts into the database without modifying the files."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session, sessionmaker

from .database import create_session_factory
from .models import Post, Recipe
from .post_repository import insert_missing_recipes


def load_post_store(store_path: Path) -> list[Recipe]:
    """Load recipes, with any attached post, from a durable per-post JSON store.

    Each file is a flat legacy record (shortcode, url, image_url, caption,
    timestamp_utc, likes, comments, typename, is_video, title, recipe_url,
    recipe_urls, recipe_names) -- this on-disk shape predates the Post/Recipe
    split and is not changing, so it's split into a Recipe and (when the
    legacy ``url`` is set) its attached Post here.
    """

    if not store_path.is_dir():
        raise ValueError("Post store must be an existing directory")

    recipes: list[Recipe] = []
    for item_path in sorted(store_path.glob("*.json")):
        try:
            payload = json.loads(item_path.read_text(encoding="utf-8"))
            shortcode = payload["shortcode"]
            recipe_names = payload.get("recipe_names") or []
            recipe = Recipe(
                id=shortcode,
                image_url=payload["image_url"],
                caption=payload["caption"],
                timestamp_utc=payload["timestamp_utc"],
                title=payload.get("title", ""),
                recipe_url=payload.get("recipe_url", ""),
                recipe_name=recipe_names[0] if recipe_names else "",
            )
            if payload.get("url", "").strip():
                recipe.post = Post(
                    shortcode=shortcode,
                    url=payload["url"],
                    typename=payload["typename"],
                    is_video=payload["is_video"],
                )
            recipes.append(recipe)
        except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
            raise ValueError(f"Invalid post item: {item_path}") from exc
    return recipes


def import_post_store(
    store_path: Path, session_factory: sessionmaker[Session], titles_path: Path | None = None
) -> int:
    """Insert missing recipes from ``store_path`` and return the number inserted.

    Existing data is preserved; explicit legacy titles only fill blank titles.
    The command can be rerun without overwriting database-authored edits.
    """

    recipes = load_post_store(store_path)
    titles: dict[str, str] = {}
    if titles_path is not None:
        try:
            titles = json.loads(titles_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError("Unable to read legacy titles JSON") from error
        if not isinstance(titles, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in titles.items()
        ):
            raise ValueError("Legacy titles must map shortcodes to strings")
        recipes = [
            replace(recipe, title=titles.get(recipe.id, "").strip() or recipe.title) for recipe in recipes
        ]
    return insert_missing_recipes(session_factory, recipes, titles=titles)


def main() -> None:
    """Run the one-time, repeatable file-store import command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        required=True,
        type=Path,
        help="Path to the *_posts_items directory containing post JSON files.",
    )
    parser.add_argument("--titles", type=Path, help="Optional legacy *_titles.json sidecar.")
    args = parser.parse_args()
    load_dotenv()
    try:
        inserted = import_post_store(args.store, create_session_factory(), args.titles)
    except ValueError as error:
        parser.error(str(error))
    print(f"Imported {inserted} post(s) from {args.store}.")


if __name__ == "__main__":
    main()
