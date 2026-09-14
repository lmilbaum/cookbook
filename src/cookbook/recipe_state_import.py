"""Import exported browser recipe state without replacing database edits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from .database import create_session_factory
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
    try:
        save_recipe_state(create_session_factory(), state, revision=0)
    except RecipeStateConflict:
        parser.error("Recipe state is already initialized; no data imported.")
    except (SQLAlchemyError, RuntimeError):
        parser.error("Unable to import recipe state; check database configuration and migrations.")
    print("Imported recipe state. Source file retained.")


if __name__ == "__main__":
    main()
