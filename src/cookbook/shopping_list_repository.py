"""Database persistence for the shared cookbook shopping list."""

from __future__ import annotations

from typing import NotRequired, TypedDict, TypeGuard

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import Ingredient, ShoppingListItem


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


def save_shopping_list(
    factory: sessionmaker[Session], items: list[ShoppingItem]
) -> None:
    """Atomically replace the list, reusing ingredients by their exact names."""

    with session_scope(factory) as session:
        # Serialize whole-list replacements, including the first save.
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("LOCK TABLE ingredients, shopping_list IN EXCLUSIVE MODE"))
        _replace_items(session, items)


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
            session.execute(text("LOCK TABLE ingredients, shopping_list IN EXCLUSIVE MODE"))
        if session.scalar(select(Ingredient.id).limit(1)) is not None:
            raise ValueError("Shopping-list storage is already in use; import refused.")
        _replace_items(session, items)
