"""Database persistence for full standalone recipe pages."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import RecipePage


def load_recipe_page(factory: sessionmaker[Session], slug: str) -> str | None:
    """Return the stored HTML for a recipe page, or ``None`` if unknown."""

    with factory() as session:
        page = session.get(RecipePage, slug)
        return page.html if page is not None else None


def insert_recipe_page(factory: sessionmaker[Session], slug: str, html: str) -> bool:
    """Store a recipe page without replacing an existing one."""

    with session_scope(factory) as session:
        if session.get(RecipePage, slug) is not None:
            return False
        session.add(RecipePage(slug=slug, html=html))
    return True
