"""Database persistence for recipe types."""

from __future__ import annotations

from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import RecipeType

MAX_NAME_LENGTH = 60


class TypeRecord(TypedDict):
    """A type as exposed by the API."""

    id: int
    name: str


class DuplicateType(ValueError):
    """Another type already has this name."""


def clean_name(value: object) -> str:
    """Return the trimmed name, or raise ValueError if it is not usable."""

    if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_NAME_LENGTH:
        raise ValueError("Invalid type name")
    return value.strip()


def _record(row: RecipeType) -> TypeRecord:
    return TypeRecord(id=row.id, name=row.name)


def list_types(factory: sessionmaker[Session]) -> list[TypeRecord]:
    """Return all types alphabetically."""

    with factory() as session:
        rows = session.scalars(select(RecipeType).order_by(func.lower(RecipeType.name), RecipeType.id))
        return [_record(row) for row in rows]


def get_type(factory: sessionmaker[Session], type_id: int) -> TypeRecord | None:
    with factory() as session:
        row = session.get(RecipeType, type_id)
        return _record(row) if row else None


def create_type(factory: sessionmaker[Session], name: object) -> TypeRecord:
    """Add a type; raises ValueError if invalid, DuplicateType if it exists."""

    name = clean_name(name)
    try:
        with session_scope(factory) as session:
            row = RecipeType(name=name)
            session.add(row)
            session.flush()
            return _record(row)
    except IntegrityError as error:
        raise DuplicateType(name) from error


def rename_type(factory: sessionmaker[Session], type_id: int, name: object) -> TypeRecord | None:
    """Rename a type; returns None if it does not exist."""

    name = clean_name(name)
    try:
        with session_scope(factory) as session:
            row = session.get(RecipeType, type_id)
            if row is None:
                return None
            row.name = name
            session.flush()
            return _record(row)
    except IntegrityError as error:
        raise DuplicateType(name) from error


def delete_type(factory: sessionmaker[Session], type_id: int) -> bool:
    """Delete a type; returns whether it existed."""

    with session_scope(factory) as session:
        row = session.get(RecipeType, type_id)
        if row is None:
            return False
        session.delete(row)
        return True
