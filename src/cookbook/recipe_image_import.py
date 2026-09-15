"""Import a recipe image file into the database."""

from __future__ import annotations

import argparse
import mimetypes
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from .database import create_session_factory
from .recipe_image_repository import insert_recipe_image


def main() -> None:
    """Store a recipe image's bytes under its filename."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    args = parser.parse_args()
    load_dotenv()
    try:
        data = args.file.read_bytes()
    except OSError:
        parser.error("Unable to read recipe image file; no data imported.")
    filename = args.file.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    try:
        inserted = insert_recipe_image(create_session_factory(), filename, content_type, data)
    except (SQLAlchemyError, RuntimeError):
        parser.error("Unable to import recipe image; check database configuration and migrations.")
    if not inserted:
        parser.error(f"Recipe image '{filename}' already exists; no data imported.")
    print(f"Imported recipe image '{filename}'. Source file retained.")


if __name__ == "__main__":
    main()
