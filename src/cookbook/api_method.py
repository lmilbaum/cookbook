"""Instagram API fetch method using Instaloader."""

from __future__ import annotations

import os
import time
from datetime import UTC
from pathlib import Path
from typing import Any

from .config import AppConfig
from .dependencies import load_instaloader
from .models import Post, Recipe


class InstagramUnauthorizedError(RuntimeError):
    """Raised when Instagram API returns unauthorized (401)."""


def _post_to_recipe(post: Any) -> Recipe:
    """Convert an Instaloader post object to a recipe with its attached post."""

    dt = post.date_utc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    timestamp = dt.astimezone(UTC).isoformat()

    recipe = Recipe(
        id=post.shortcode,
        image_url=str(getattr(post, "url", "") or ""),
        caption=(post.caption or "").strip(),
        timestamp_utc=timestamp,
    )
    recipe.post = Post(
        shortcode=post.shortcode,
        url=f"https://www.instagram.com/p/{post.shortcode}/",
        typename=post.typename,
        is_video=post.is_video,
    )
    return recipe


def _validate_fetch_settings(config: AppConfig) -> None:
    """Validate fetch-related numeric settings."""

    if config.request_delay_seconds < 0:
        raise ValueError("--request-delay-seconds must be >= 0")
    if config.max_fetch_attempts < 1:
        raise ValueError("--max-fetch-attempts must be >= 1")
    if config.retry_wait_seconds < 1:
        raise ValueError("--retry-wait-seconds must be >= 1")


def _build_loader(instaloader: Any, login_user: str, session_file: str) -> Any:
    """Create and optionally authenticate an Instaloader instance."""

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_video_thumbnails=False,
        download_videos=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )

    if not login_user:
        return loader

    session_path = Path(session_file)
    if session_path.exists():
        loader.load_session_from_file(login_user, str(session_path))
        return loader

    password = os.getenv("INSTAGRAM_PASSWORD")
    if not password:
        raise ValueError(
            "INSTAGRAM_PASSWORD is required when no session file exists. "
            "Set it and run again to create the session."
        )
    loader.login(login_user, password)
    loader.save_session_to_file(str(session_path))
    return loader


def _is_unauthorized_error(message: str) -> bool:
    """Check whether an error message indicates unauthorized access."""

    return "401 Unauthorized" in message


def _is_rate_limited_error(message: str) -> bool:
    """Check whether an error message indicates Instagram rate limiting."""

    return "Please wait a few minutes before you try again." in message


def fetch_posts_api(
    config: AppConfig,
    login_user: str,
    seen_shortcodes: set[str] | None = None,
) -> list[Recipe]:
    """Fetch posts using Instaloader API with retry/backoff."""

    _validate_fetch_settings(config)
    instaloader = load_instaloader()
    seen_shortcodes = seen_shortcodes or set()

    for attempt in range(1, config.max_fetch_attempts + 1):
        loader = _build_loader(instaloader, login_user, config.session_file)

        try:
            profile = instaloader.Profile.from_username(loader.context, config.username)
            recipes: list[Recipe] = []

            # Instaloader yields posts from newest to oldest by default.
            for post in profile.get_posts():
                if post.shortcode in seen_shortcodes:
                    continue
                recipes.append(_post_to_recipe(post))
                if 0 < config.limit <= len(recipes):
                    break
                if config.request_delay_seconds > 0:
                    time.sleep(config.request_delay_seconds)

            if config.reverse:
                recipes.reverse()
            return recipes
        except instaloader.exceptions.ConnectionException as exc:
            message = str(exc)
            if _is_unauthorized_error(message):
                raise InstagramUnauthorizedError(message) from exc
            if not _is_rate_limited_error(message) or attempt >= config.max_fetch_attempts:
                raise

            wait_seconds = config.retry_wait_seconds * attempt
            print(
                f"Instagram rate limit hit. Waiting {wait_seconds}s "
                f"before retry {attempt + 1}/{config.max_fetch_attempts}..."
            )
            time.sleep(wait_seconds)

    raise RuntimeError("Failed to fetch posts after retry attempts.")
