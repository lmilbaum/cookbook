"""Database persistence for recipe thumbs up/down ratings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import RecipeRating


def parse_rating(value: object) -> str | None:
    """Accept 'up', 'down', or None (clear). Anything else is rejected."""
    if value is None:
        return None
    if value == "up" or value == "down":
        return value
    raise ValueError(f"Invalid rating: {value!r}")


def get_rating(factory: sessionmaker[Session], recipe_id: str) -> str | None:
    with session_scope(factory) as session:
        row = session.get(RecipeRating, recipe_id)
        return row.rating if row else None


def set_rating(factory: sessionmaker[Session], recipe_id: str, rating: str | None) -> None:
    with session_scope(factory) as session:
        row = session.get(RecipeRating, recipe_id)
        if rating is None:
            if row:
                session.delete(row)
        elif row:
            row.rating = rating
        else:
            session.add(RecipeRating(recipe_id=recipe_id, rating=rating))


def all_ratings(factory: sessionmaker[Session]) -> dict[str, str]:
    with session_scope(factory) as session:
        rows = session.execute(select(RecipeRating)).scalars().all()
        return {r.recipe_id: r.rating for r in rows}


def move_rating(session: Session, from_id: str, to_id: str) -> None:
    """Move a rating from one recipe id to another. On conflict, keep the target's rating."""
    src = session.get(RecipeRating, from_id)
    if src:
        dst = session.get(RecipeRating, to_id)
        if not dst:
            session.add(RecipeRating(recipe_id=to_id, rating=src.rating))
        session.delete(src)
