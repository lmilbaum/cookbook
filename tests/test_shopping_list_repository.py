"""Shopping-list persistence and migration tests without a running database."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from cookbook.models import Ingredient, ShoppingListItem
from cookbook.shopping_list_repository import ShoppingItem, load_shopping_list, save_shopping_list


def test_migration_and_shopping_list_lifecycle() -> None:
    path = Path(__file__).parents[1] / "migrations/versions/20260911_01_shopping_lists.py"
    spec = importlib.util.spec_from_file_location("shopping_list_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    factory = sessionmaker(bind=engine)
    assert load_shopping_list(factory) == []
    items: list[ShoppingItem] = [
        {"id": "second", "name": "חלב", "done": True, "quantity": "2"},
        {"id": "first", "name": "Eggs", "done": False},
    ]
    save_shopping_list(factory, items)
    assert load_shopping_list(factory) == list(reversed(items))
    with factory() as session:
        assert len(session.scalars(select(Ingredient)).all()) == 2
        assert len(session.scalars(select(ShoppingListItem)).all()) == 2
    save_shopping_list(factory, items[1:])
    assert load_shopping_list(factory) == items[1:]
    save_shopping_list(factory, [])
    assert load_shopping_list(factory) == []

    # Clearing the list retains reusable ingredient records.
    with factory() as session:
        assert len(session.scalars(select(Ingredient)).all()) == 2
    save_shopping_list(factory, items)
    # A failed replacement must roll back deletions as well as new ingredients.
    with pytest.raises(IntegrityError):
        save_shopping_list(factory, [
            {"id": "duplicate", "name": "Apple", "done": False},
            {"id": "duplicate", "name": "Banana", "done": False},
        ])
    assert load_shopping_list(factory) == list(reversed(items))
    with factory() as session:
        assert len(session.scalars(select(Ingredient)).all()) == 2

    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert "shopping_list" not in inspect(connection).get_table_names()
        assert "ingredients" not in inspect(connection).get_table_names()
    engine.dispose()


def test_import_refuses_to_overwrite_or_resurrect_items() -> None:
    from cookbook.database import Base
    from cookbook.shopping_list_repository import import_shopping_list

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    items: list[ShoppingItem] = [{"id": "milk", "name": "Milk", "done": True}]
    import_shopping_list(factory, items)
    assert load_shopping_list(factory) == items
    with pytest.raises(ValueError, match="already in use"):
        import_shopping_list(factory, items)
    save_shopping_list(factory, [])
    with pytest.raises(ValueError, match="already in use"):
        import_shopping_list(factory, items)
    assert load_shopping_list(factory) == []
    engine.dispose()
