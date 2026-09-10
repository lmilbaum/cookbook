"""Import file-backed recipe posts into the database without modifying the files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from .database import create_session_factory
from .models import PostItem
from .post_repository import insert_missing_posts


def load_post_store(store_path: Path) -> list[PostItem]:
    """Load post items from a durable per-post JSON store."""

    if not store_path.exists():
        return []

    posts: list[PostItem] = []
    for item_path in sorted(store_path.glob("*.json")):
        try:
            payload = json.loads(item_path.read_text(encoding="utf-8"))
            posts.append(PostItem(**payload))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Invalid post item: {item_path}") from exc
    return posts


def import_post_store(store_path: Path, session_factory: sessionmaker[Session]) -> int:
    """Insert missing posts from ``store_path`` and return the number inserted.

    Existing rows are deliberately left unchanged so the command is safe to
    rerun and cannot overwrite database-authored edits.
    """

    return insert_missing_posts(session_factory, load_post_store(store_path))


def main() -> None:
    """Run the one-time, repeatable file-store import command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        required=True,
        type=Path,
        help="Path to the *_posts_items directory containing post JSON files.",
    )
    args = parser.parse_args()
    inserted = import_post_store(args.store, create_session_factory())
    print(f"Imported {inserted} post(s) from {args.store}.")


if __name__ == "__main__":
    main()
