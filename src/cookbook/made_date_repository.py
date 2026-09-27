"""Database persistence for recipe made-on dates."""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import RecipeMadeDate

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_made_on(value: object) -> date:
    """Strict ISO date parse. Rejects compact forms like 20260927."""
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        raise ValueError(f"Invalid date: {value!r}")
    return date.fromisoformat(value)


def list_made_dates(factory: sessionmaker[Session], recipe_id: str) -> list[str]:
    """Return ISO date strings, newest first."""
    with factory() as session:
        rows = (
            session.query(RecipeMadeDate)
            .filter_by(recipe_id=recipe_id)
            .order_by(RecipeMadeDate.made_on.desc())
            .all()
        )
        return [r.made_on.isoformat() for r in rows]


def add_made_date(factory: sessionmaker[Session], recipe_id: str, made_on: date) -> bool:
    """Returns True if the date was newly added, False if it already existed."""
    try:
        with session_scope(factory) as session:
            session.add(RecipeMadeDate(recipe_id=recipe_id, made_on=made_on))
        return True
    except IntegrityError:
        return False


def remove_made_date(factory: sessionmaker[Session], recipe_id: str, made_on: date) -> bool:
    """Returns True if the date existed and was removed."""
    with session_scope(factory) as session:
        row = session.get(RecipeMadeDate, (recipe_id, made_on))
        if row is None:
            return False
        session.delete(row)
        return True


def move_made_dates(session: Session, from_id: str, to_id: str) -> None:
    """Move all made-dates from one recipe id to another. On conflict, drop the source row."""
    rows = session.query(RecipeMadeDate).filter_by(recipe_id=from_id).all()
    for row in rows:
        existing = session.get(RecipeMadeDate, (to_id, row.made_on))
        if existing is None:
            session.add(RecipeMadeDate(recipe_id=to_id, made_on=row.made_on))
        session.delete(row)
