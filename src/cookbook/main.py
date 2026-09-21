"""Fetch Instagram profile posts and store them in the database."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .api_method import InstagramUnauthorizedError, fetch_posts_api
from .browser_scraper import fetch_posts_browser
from .config import AppConfig, load_config, parse_args, resolve_from
from .database import create_session_factory
from .dependencies import load_dotenv_loader
from .models import Recipe
from .post_repository import insert_missing_recipes, load_recipes
from .recipe_photo_fetch import store_missing_photos


def _cooldown_marker_path(session_file: str) -> Path:
    """Store API cooldown metadata next to the session file."""

    session_path = Path(session_file)
    return session_path.with_name(f"{session_path.name}.api401.json")


def _read_cooldown_until(cooldown_path: Path) -> datetime | None:
    """Read cooldown-until timestamp from marker file when present."""

    if not cooldown_path.exists():
        return None

    try:
        payload = json.loads(cooldown_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    raw_until = payload.get("until_utc")
    if not isinstance(raw_until, str) or not raw_until:
        return None

    try:
        parsed = datetime.fromisoformat(raw_until)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _write_cooldown(cooldown_path: Path, cooldown_hours: int) -> datetime | None:
    """Persist cooldown-until timestamp after API 401."""

    if cooldown_hours <= 0:
        return None

    until_utc = datetime.now(UTC) + timedelta(hours=cooldown_hours)
    cooldown_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"until_utc": until_utc.isoformat()}
    cooldown_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return until_utc


def _fetch_posts_browser_only(
    config: AppConfig,
    login_user: str,
    password: str,
    seen_shortcodes: set[str],
) -> list[Recipe]:
    """Fetch via browser scraper, validating required credentials."""

    if not login_user:
        raise ValueError("Browser fallback requires INSTAGRAM_USERNAME or login_user in config.")
    if not password:
        raise ValueError("Browser fallback requires INSTAGRAM_PASSWORD.")

    return fetch_posts_browser(
        config.username,
        config.limit,
        login_user=login_user,
        login_pass=password,
        reverse=config.reverse,
        session_file=config.session_file,
        seen_shortcodes=seen_shortcodes,
        feed_position_from_end=config.feed_position_from_end,
    )


def _fetch_posts_with_fallback(
    config: AppConfig,
    login_user: str,
    password: str,
    seen_shortcodes: set[str],
) -> list[Recipe]:
    """Try API first, then fall back to browser scraping on unauthorized response."""

    if config.use_browser:
        return _fetch_posts_browser_only(config, login_user, password, seen_shortcodes)

    cooldown_path = _cooldown_marker_path(config.session_file)
    cooldown_until = _read_cooldown_until(cooldown_path)
    now_utc = datetime.now(UTC)

    if cooldown_until is not None and now_utc < cooldown_until:
        remaining = cooldown_until - now_utc
        remaining_minutes = int(remaining.total_seconds() // 60)
        print(
            "Skipping API due to active 401 cooldown "
            f"({remaining_minutes} minute(s) remaining)."
        )
        return _fetch_posts_browser_only(config, login_user, password, seen_shortcodes)

    try:
        return fetch_posts_api(config, login_user, seen_shortcodes)
    except InstagramUnauthorizedError:
        cooldown_until = _write_cooldown(cooldown_path, config.api_401_cooldown_hours)
        print("Instagram API returned 401. Switching to browser scraping...")
        if cooldown_until is not None:
            print(f"API cooldown active until {cooldown_until.isoformat()}")
        return _fetch_posts_browser_only(config, login_user, password, seen_shortcodes)


def main() -> None:  # pylint: disable=too-many-branches,too-many-locals,too-many-statements
    """Program entrypoint."""

    args = parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)

    if args.limit is not None:
        config.limit = args.limit
    if args.feed_position_from_end is not None:
        config.feed_position_from_end = args.feed_position_from_end

    if config.limit < 0:
        raise ValueError("Config key 'limit' must be >= 0.")
    if config.feed_position_from_end < 0:
        raise ValueError("--feed-position-from-end must be >= 0.")

    base_dir = config_path.parent.resolve()
    env_path = resolve_from(base_dir, config.env_file)
    session_path = resolve_from(base_dir, config.session_file)
    load_dotenv = load_dotenv_loader()
    load_dotenv(env_path)

    login_user = config.login_user or os.getenv("INSTAGRAM_USERNAME", "").strip()
    password = os.getenv("INSTAGRAM_PASSWORD", "").strip()
    config.session_file = str(session_path)

    session_factory = create_session_factory()
    fetch_seen_shortcodes: set[str] = set()
    existing_recipes: list[Recipe] = []
    if not config.ignore_cached_posts:
        existing_recipes = load_recipes(session_factory, reverse=config.reverse)
        fetch_seen_shortcodes = {
            recipe.post.shortcode for recipe in existing_recipes if recipe.post is not None
        }
        if config.feed_position_from_end > 0:
            fetch_seen_shortcodes = {
                recipe.post.shortcode for recipe in existing_recipes if recipe.post is not None
            }

    fetch_config = config
    should_fetch = True
    if not config.ignore_cached_posts and config.limit > 0:
        if config.feed_position_from_end > 0:
            # A targeted position is a request for one candidate, independent
            # of how many posts have already been imported.
            fetch_config = replace(config, limit=1)
        else:
            remaining_slots = max(config.limit - len(existing_recipes), 0)
            should_fetch = remaining_slots > 0
            if should_fetch:
                fetch_config = replace(config, limit=remaining_slots)

    new_recipes = (
        _fetch_posts_with_fallback(fetch_config, login_user, password, fetch_seen_shortcodes)
        if should_fetch
        else []
    )
    if config.ignore_cached_posts:
        print(f"Fetched {len(new_recipes)} posts for @{config.username}")
        print("Skipped database writes (strict window mode)")
        return

    inserted = insert_missing_recipes(session_factory, new_recipes)
    photos = store_missing_photos(session_factory, new_recipes)
    total = len(load_recipes(session_factory, reverse=config.reverse))
    print(f"Fetched {len(new_recipes)} new posts for @{config.username}; stored {inserted} recipes and {photos} photos")
    print(f"Total recipes in the database: {total}")
    print("Post source of truth: PostgreSQL. Run the server to view the cookbook.")


if __name__ == "__main__":
    main()
