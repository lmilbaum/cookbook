"""Explicitly import a legacy shopping list without modifying its source file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .database import create_session_factory
from .shopping_list_repository import import_shopping_list, valid_items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    args = parser.parse_args()
    load_dotenv()
    try:
        items = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        parser.error("Unable to read shopping-list JSON.")
    if not valid_items(items):
        parser.error("Invalid shopping list; no data imported.")
    try:
        import_shopping_list(create_session_factory(), items)
    except ValueError as error:
        parser.error(str(error))
    print(f"Imported {len(items)} shopping item(s). Source file retained.")


if __name__ == "__main__":
    main()
