"""Database persistence for the shared cookbook shopping list."""

from __future__ import annotations

from typing import NotRequired, TypedDict, TypeGuard

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import Ingredient, ShoppingListItem, ShoppingListState


class ShoppingItem(TypedDict):
    """Validated shopping-list payload, compatible with the existing API."""

    id: str
    name: str
    done: bool
    quantity: NotRequired[str]


def load_shopping_list(factory: sessionmaker[Session]) -> list[ShoppingItem]:
    """Return shopping items alphabetically by ingredient name."""

    with factory() as session:
        rows = session.execute(
            select(ShoppingListItem, Ingredient.name)
            .join(Ingredient)
            .order_by(func.lower(Ingredient.name), Ingredient.name, ShoppingListItem.id)
        )
        items: list[ShoppingItem] = []
        for row, name in rows:
            item = ShoppingItem(id=row.id, name=name, done=row.done)
            if row.quantity is not None:
                item["quantity"] = row.quantity
            items.append(item)
        return items


class ShoppingListConflict(ValueError):
    """A stale client tried to replace the shared list."""


def load_shopping_state(factory: sessionmaker[Session]) -> dict[str, int | list[ShoppingItem]]:
    """Read items and revision in one consistent transaction."""
    with session_scope(factory) as session:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("LOCK TABLE shopping_list_state, ingredients, shopping_list IN SHARE MODE"))
        row = session.get(ShoppingListState, 1)
        # Bind the existing reader to this transaction.
        items = load_shopping_list(sessionmaker(bind=session.connection()))
        return {"items": items, "revision": row.revision if row else 0}


def save_shopping_list(
    factory: sessionmaker[Session], items: list[ShoppingItem], revision: int | None = None
) -> int:
    """Atomically replace a list; optionally require the client's revision."""
    if revision is not None and (type(revision) is not int or revision < 0):
        raise ValueError("Invalid revision")
    with session_scope(factory) as session:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("LOCK TABLE shopping_list_state, ingredients, shopping_list IN EXCLUSIVE MODE"))
        row = session.get(ShoppingListState, 1)
        current = row.revision if row else 0
        if revision is not None and revision != current:
            raise ShoppingListConflict("Shopping list changed; reload before saving")
        _replace_items(session, items)
        if row is None:
            session.add(ShoppingListState(id=1, revision=current + 1))
        else:
            row.revision += 1
    return current + 1


def _replace_items(session: Session, items: list[ShoppingItem]) -> None:
    session.execute(delete(ShoppingListItem))
    for item in items:
        ingredient = session.scalar(
            select(Ingredient).where(Ingredient.name == item["name"])
        )
        if ingredient is None:
            ingredient = Ingredient(name=item["name"])
            session.add(ingredient)
            session.flush()
        session.add(ShoppingListItem(
            id=item["id"], ingredient_id=ingredient.id,
            quantity=item.get("quantity"), done=item["done"],
        ))


def valid_items(value: object) -> TypeGuard[list[ShoppingItem]]:
    """Validate fields before writing a list or importing legacy JSON."""

    if not isinstance(value, list):
        return False
    ids: set[str] = set()
    for item in value:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not isinstance(item.get("name"), str)
            or len(item["name"]) > 120
            or not isinstance(item.get("done"), bool)
            or ("quantity" in item and not isinstance(item["quantity"], str))
            or item["id"] in ids
            or set(item) - {"id", "name", "done", "quantity"}
        ):
            return False
        ids.add(item["id"])
    return True


def import_shopping_list(factory: sessionmaker[Session], items: list[ShoppingItem]) -> None:
    """Import only into unused storage; never resurrect a previously cleared list."""

    with session_scope(factory) as session:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("LOCK TABLE shopping_list_state, ingredients, shopping_list IN EXCLUSIVE MODE"))
        if session.get(ShoppingListState, 1) is not None or session.scalar(select(Ingredient.id).limit(1)) is not None:
            raise ValueError("Shopping-list storage is already in use; import refused.")
        _replace_items(session, items)
        session.add(ShoppingListState(id=1, revision=1))
