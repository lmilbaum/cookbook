"""Exercise migrations and concurrent saves in a disposable PostgreSQL schema.

Run with DATABASE_URL set. Existing application tables are never modified.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from cookbook.database import database_url
from cookbook.recipe_state_repository import load_recipe_state, save_recipe_state
from cookbook.shopping_list_repository import (
    ShoppingListConflict, load_shopping_state, save_shopping_list,
)


def main() -> None:
    original_url = database_url()
    admin = create_engine(original_url)
    schema = f"migration_check_{uuid4().hex}"
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_url = make_url(original_url).update_query_dict({"options": f"-csearch_path={schema}"})
    os.environ["DATABASE_URL"] = test_url.render_as_string(hide_password=False)
    engine = create_engine(test_url)
    try:
        config = Config(toml_file=str(Path(__file__).resolve().parents[1] / "pyproject.toml"))
        command.upgrade(config, "20260913_01")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO ingredients (name) VALUES ('Migration test')"))
            connection.execute(text("INSERT INTO shopping_list (id, ingredient_id, done) VALUES ('test', 1, false)"))
        command.upgrade(config, "head")
        factory = sessionmaker(bind=engine)
        before = load_shopping_state(factory)
        assert before["revision"] == 1 and len(before["items"]) == 1
        def save(index):
            try:
                return save_shopping_list(factory, [{"id": str(index), "name": "Test", "done": False}], revision=1)
            except ShoppingListConflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(save, [1, 2]))
        assert results.count(2) == 1 and results.count("conflict") == 1
        state = {"overrides": {"test": {"notes": "Migration test"}}, "custom": []}
        save_recipe_state(factory, state, 0)
        engine.dispose()
        engine = create_engine(test_url)
        factory = sessionmaker(bind=engine)
        assert load_shopping_state(factory)["revision"] == 2
        assert load_recipe_state(factory)["state"] == state
        command.check(config)
        command.downgrade(config, "20260913_01")
        command.upgrade(config, "head")
        assert len(load_shopping_state(factory)["items"]) == 1
        print("PostgreSQL migration, concurrent writes, reconnect persistence, and schema checks passed.")
    finally:
        engine.dispose()
        os.environ["DATABASE_URL"] = original_url
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    main()
