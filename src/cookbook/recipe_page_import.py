"""Import a standalone recipe HTML page into the database."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from .database import create_session_factory
from .recipe_page_repository import insert_recipe_page


def main() -> None:
    """Store a recipe page's HTML under its filename slug."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    args = parser.parse_args()
    load_dotenv()
    try:
        html = args.file.read_text(encoding="utf-8")
    except OSError:
        parser.error("Unable to read recipe page file; no data imported.")
    slug = args.file.stem
    try:
        inserted = insert_recipe_page(create_session_factory(), slug, html)
    except (SQLAlchemyError, RuntimeError):
        parser.error("Unable to import recipe page; check database configuration and migrations.")
    if not inserted:
        parser.error(f"Recipe page '{slug}' already exists; no data imported.")
    print(f"Imported recipe page '{slug}'. Source file retained.")


if __name__ == "__main__":
    main()
