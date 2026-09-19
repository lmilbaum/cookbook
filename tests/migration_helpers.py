"""Load Alembic revision modules by file name for tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

_VERSIONS = Path(__file__).parents[1] / "migrations" / "versions"


def load_migration(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), _VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RENAME_TABLES = "20260919_02_rename_tables_to_match_models.py"
