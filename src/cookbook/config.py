"""Configuration parsing and validation."""

from __future__ import annotations

import argparse
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:  # pylint: disable=too-many-instance-attributes
    """Runtime configuration loaded from TOML."""

    username: str
    limit: int
    output: str
    reverse: bool
    login_user: str
    session_file: str
    env_file: str
    request_delay_seconds: float
    max_fetch_attempts: int
    retry_wait_seconds: int
    use_browser: bool
    api_401_cooldown_hours: int
    ignore_cached_posts: bool
    feed_position_from_end: int


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Fetch Instagram posts using a TOML config file."
    )
    parser.add_argument("--config", default="cookbook.toml", help="Path to TOML config file")
    return parser.parse_args()


def load_config(config_path: Path) -> AppConfig:  # pylint: disable=too-many-branches
    """Load and validate app configuration from TOML."""

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "rb") as file:
        raw = tomllib.load(file)

    username = raw.get("username", "")
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Config key 'username' is required and must be a non-empty string.")

    limit = raw.get("limit", 0)
    if not isinstance(limit, int):
        raise TypeError("Config key 'limit' must be an integer.")

    output = raw.get("output", "instagram_posts.json")
    if not isinstance(output, str) or not output.strip():
        raise ValueError("Config key 'output' must be a non-empty string.")

    reverse = raw.get("reverse", False)
    if not isinstance(reverse, bool):
        raise TypeError("Config key 'reverse' must be true/false.")

    login_user = raw.get("login_user", "")
    if not isinstance(login_user, str):
        raise TypeError("Config key 'login_user' must be a string.")

    session_file = raw.get("session_file", ".instagram.session")
    if not isinstance(session_file, str) or not session_file.strip():
        raise ValueError("Config key 'session_file' must be a non-empty string.")

    env_file = raw.get("env_file", ".env")
    if not isinstance(env_file, str) or not env_file.strip():
        raise ValueError("Config key 'env_file' must be a non-empty string.")

    request_delay_seconds = raw.get("request_delay_seconds", 1.5)
    if not isinstance(request_delay_seconds, (int, float)):
        raise TypeError("Config key 'request_delay_seconds' must be a number.")

    max_fetch_attempts = raw.get("max_fetch_attempts", 3)
    if not isinstance(max_fetch_attempts, int):
        raise TypeError("Config key 'max_fetch_attempts' must be an integer.")

    retry_wait_seconds = raw.get("retry_wait_seconds", 180)
    if not isinstance(retry_wait_seconds, int):
        raise TypeError("Config key 'retry_wait_seconds' must be an integer.")

    use_browser = raw.get("use_browser", False)
    if not isinstance(use_browser, bool):
        raise TypeError("Config key 'use_browser' must be true/false.")

    api_401_cooldown_hours = raw.get("api_401_cooldown_hours", 24)
    if not isinstance(api_401_cooldown_hours, int):
        raise TypeError("Config key 'api_401_cooldown_hours' must be an integer.")
    if api_401_cooldown_hours < 0:
        raise ValueError("Config key 'api_401_cooldown_hours' must be >= 0.")

    ignore_cached_posts = raw.get("ignore_cached_posts", False)
    if not isinstance(ignore_cached_posts, bool):
        raise TypeError("Config key 'ignore_cached_posts' must be true/false.")

    feed_position_from_end = raw.get("feed_position_from_end", 0)
    if not isinstance(feed_position_from_end, int):
        raise TypeError("Config key 'feed_position_from_end' must be an integer.")
    if feed_position_from_end < 0:
        raise ValueError("Config key 'feed_position_from_end' must be >= 0.")

    return AppConfig(
        username=username.strip(),
        limit=limit,
        output=output.strip(),
        reverse=reverse,
        login_user=login_user.strip(),
        session_file=session_file.strip(),
        env_file=env_file.strip(),
        request_delay_seconds=float(request_delay_seconds),
        max_fetch_attempts=max_fetch_attempts,
        retry_wait_seconds=retry_wait_seconds,
        use_browser=use_browser,
        api_401_cooldown_hours=api_401_cooldown_hours,
        ignore_cached_posts=ignore_cached_posts,
        feed_position_from_end=feed_position_from_end,
    )


def resolve_from(base_dir: Path, value: str) -> Path:
    """Resolve a path relative to the config directory when needed."""

    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path
