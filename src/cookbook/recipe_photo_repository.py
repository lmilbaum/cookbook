"""Database persistence for recipe card photos."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import RecipePhoto


def load_recipe_photo(factory: sessionmaker[Session], recipe_id: str) -> tuple[bytes, str] | None:
    """Return the stored bytes and content type for a recipe's photo, or ``None``."""

    with factory() as session:
        photo = session.get(RecipePhoto, recipe_id)
        return (photo.data, photo.content_type) if photo is not None else None


def photo_ids(factory: sessionmaker[Session]) -> set[str]:
    """Ids of every recipe that has a stored photo."""

    with factory() as session:
        return set(session.scalars(select(RecipePhoto.recipe_id)))


def insert_recipe_photo(
    factory: sessionmaker[Session], recipe_id: str, content_type: str, data: bytes
) -> bool:
    """Store a recipe photo without replacing an existing one."""

    with session_scope(factory) as session:
        if session.get(RecipePhoto, recipe_id) is not None:
            return False
        session.add(RecipePhoto(recipe_id=recipe_id, content_type=content_type, data=data))
    return True
