"""Database persistence for recipe page images."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import RecipeImage


def load_recipe_image(factory: sessionmaker[Session], filename: str) -> tuple[bytes, str] | None:
    """Return the stored bytes and content type for a recipe image, or ``None``."""

    with factory() as session:
        image = session.get(RecipeImage, filename)
        return (image.data, image.content_type) if image is not None else None


def insert_recipe_image(
    factory: sessionmaker[Session], filename: str, content_type: str, data: bytes
) -> bool:
    """Store a recipe image without replacing an existing one."""

    with session_scope(factory) as session:
        if session.get(RecipeImage, filename) is not None:
            return False
        session.add(RecipeImage(filename=filename, content_type=content_type, data=data))
    return True
