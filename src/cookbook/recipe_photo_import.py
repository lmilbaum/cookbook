"""Import cached recipe photo files (*_posts_assets/) into the database."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from .database import create_session_factory
from .recipe_photo_fetch import PHOTO_CONTENT_TYPES
from .recipe_photo_repository import insert_recipe_photo


def main() -> None:
    """Store every photo in a directory under its file stem (the recipe id)."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    load_dotenv()
    files = sorted(
        path for path in args.directory.glob("*")
        if path.is_file() and path.suffix.lower() in PHOTO_CONTENT_TYPES
    )
    if not files:
        parser.error("No photo files found; no data imported.")
    try:
        factory = create_session_factory()
        imported = sum(
            insert_recipe_photo(factory, path.stem, PHOTO_CONTENT_TYPES[path.suffix.lower()], path.read_bytes())
            for path in files
        )
    except (SQLAlchemyError, RuntimeError, OSError):
        parser.error("Unable to import photos; check database configuration and migrations.")
    print(f"Imported {imported} of {len(files)} photos; existing photos were kept. Source files retained.")


if __name__ == "__main__":
    main()
