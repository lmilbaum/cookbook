"""Import file-backed recipe posts into the database without modifying the files."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from sqlalchemy.orm import Session, sessionmaker

from .database import create_session_factory
from .models import PostItem
from .post_repository import insert_missing_posts


def load_post_store(store_path: Path) -> list[PostItem]:
    """Load post items from a durable per-post JSON store."""

    if not store_path.is_dir():
        raise ValueError("Post store must be an existing directory")

    posts: list[PostItem] = []
    for item_path in sorted(store_path.glob("*.json")):
        try:
            payload = json.loads(item_path.read_text(encoding="utf-8"))
            posts.append(PostItem(**payload))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Invalid post item: {item_path}") from exc
    return posts


def import_post_store(
    store_path: Path, session_factory: sessionmaker[Session], titles_path: Path | None = None
) -> int:
    """Insert missing posts from ``store_path`` and return the number inserted.

    Existing data is preserved; explicit legacy titles only fill blank titles.
    The command can be rerun without overwriting database-authored edits.
    """

    posts = load_post_store(store_path)
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
        posts = [replace(post, title=titles.get(post.shortcode, "").strip() or post.title) for post in posts]
    return insert_missing_posts(session_factory, posts, titles=titles)


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
