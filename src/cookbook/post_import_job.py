"""Import one unseen post from the feed end, directly through the scraper."""
from __future__ import annotations

import argparse
import os
import re as _re
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .browser_scraper import IncompleteProfileError, fetch_post_by_url_browser, fetch_posts_browser
from .config import load_config, resolve_from

_INSTAGRAM_MEDIA_RE = _re.compile(r"instagram\.com(/(?:p|reel)/[A-Za-z0-9_-]+)")
from .database import create_session_factory
from .import_service import REASON_PREFIX
from .models import Post, Recipe
from .post_repository import insert_missing_recipes
from .recipe_photo_fetch import store_missing_photos


def _promote_instagram_attrs(recipe: Recipe) -> None:
    """Copy transient scraper attrs to the persistent source/source_name columns."""
    source = getattr(recipe, "_instagram_username", "")
    source_name = getattr(recipe, "_instagram_display_name", "")
    if source:
        recipe.source = source
    if source_name:
        recipe.source_name = source_name


def import_next_post(root: Path, factory: sessionmaker[Session]) -> int:
    """Skip every stored post, including hidden posts, and import one candidate."""
    config = load_config(root / "cookbook.toml")
    load_dotenv(resolve_from(root, config.env_file))
    with factory() as session:
        seen = set(session.scalars(select(Post.shortcode)))
    recipes = fetch_posts_browser(
        config.username, limit=1, headless=True,
        login_user=config.login_user or os.getenv("INSTAGRAM_USERNAME", "").strip(),
        login_pass=os.getenv("INSTAGRAM_PASSWORD", "").strip(),
        session_file=str(resolve_from(root, config.session_file)),
        seen_shortcodes=seen, feed_position_from_end=1,
    )
    recipes = [
        recipe for recipe in recipes if recipe.post is not None and recipe.post.shortcode not in seen
    ][:1]
    if not recipes:
        return 0
    for recipe in recipes:
        _promote_instagram_attrs(recipe)
    imported = insert_missing_recipes(factory, recipes)
    store_missing_photos(factory, recipes)
    return imported


def import_post_by_url(
    root: Path, factory: sessionmaker[Session], url: str
) -> tuple[str, str, str] | None:
    """Scrape a specific Instagram post URL and store it in the database.

    Returns ``(shortcode, instagram_username, display_name)`` on success, or
    None if the URL is not a recognised Instagram post/reel path, the browser
    session is missing, or scraping fails.  Both ``instagram_username`` and
    ``display_name`` are empty strings when they could not be extracted.
    """

    match = _INSTAGRAM_MEDIA_RE.search(url)
    if not match:
        return None
    media_path = match.group(1).rstrip("/") + "/"

    config = load_config(root / "cookbook.toml")
    load_dotenv(resolve_from(root, config.env_file))
    session_file = str(resolve_from(root, config.session_file))

    recipe = fetch_post_by_url_browser(media_path, session_file=session_file)
    if recipe is None:
        return None

    # Capture before session operations expire mapped attrs.
    _promote_instagram_attrs(recipe)
    shortcode = recipe.id
    source = recipe.source if getattr(recipe, "_instagram_username", "") else ""
    source_name = recipe.source_name if getattr(recipe, "_instagram_display_name", "") else ""
    insert_missing_recipes(factory, [recipe])
    store_missing_photos(factory, [recipe])
    return shortcode, source, source_name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    load_dotenv(root / ".env")
    try:
        imported = import_next_post(root, create_session_factory())
    except IncompleteProfileError as error:
        print(f"{REASON_PREFIX}{error.code}", file=sys.stderr)
        raise SystemExit(4) from None
    raise SystemExit(0 if imported else 3)


if __name__ == "__main__":
    main()
