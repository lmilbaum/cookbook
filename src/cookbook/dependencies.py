"""Lazy imports for optional dependencies."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any


def load_instaloader() -> Any:
    """Import instaloader with a user-facing dependency error."""

    try:
        return importlib.import_module("instaloader")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing dependency 'instaloader'. Install dependencies with `uv sync`."
        ) from exc


def load_dotenv_loader() -> Callable[[str], bool]:
    """Import python-dotenv and return its load function."""

    try:
        module = importlib.import_module("dotenv")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing dependency 'python-dotenv'. Install dependencies with `uv sync`."
        ) from exc

    load_dotenv = getattr(module, "load_dotenv", None)
    if load_dotenv is None:
        raise AttributeError("python-dotenv is installed but load_dotenv is unavailable.")
    return load_dotenv
