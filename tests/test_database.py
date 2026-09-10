"""Tests for database configuration without requiring PostgreSQL."""

from __future__ import annotations

import pytest

from cookbook.database import create_database_engine, database_url
from cookbook.config import parse_args


def test_database_url_uses_psycopg_for_plain_postgresql_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost/cookbook")

    assert database_url() == "postgresql+psycopg://user:password@localhost/cookbook"
    assert create_database_engine().url.drivername == "postgresql+psycopg"


def test_database_url_requires_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database_url()


def test_parse_args_accepts_one_off_feed_position_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["cookbook", "--limit", "1", "--feed-position-from-end", "1"],
    )

    args = parse_args()

    assert args.limit == 1
    assert args.feed_position_from_end == 1
