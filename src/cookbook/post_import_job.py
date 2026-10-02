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

_INSTAGRAM_MEDIA_RE = _re.compile(r"instagram\.com(/(?:p|reels?)/[A-Za-z0-9_-]+)")
from .database import create_session_factory, session_scope
from .import_service import REASON_PREFIX
from .models import Post, Recipe
from .post_repository import insert_missing_recipes
from .recipe_photo_fetch import download_photo, store_missing_photos
from .recipe_photo_repository import replace_recipe_photo


def _promote_instagram_attrs(recipe: Recipe) -> None:
    """Copy transient scraper attrs to the persistent source/source_name columns."""
    source = getattr(recipe, "_instagram_username", "")
    source_name = getattr(recipe, "_instagram_display_name", "")
    if source:
        recipe.source = source
    if source_name:
        recipe.source_name = source_name


def populate_recipe_from_caption(
    factory: sessionmaker[Session], recipe_id: str
) -> tuple[int, dict] | None:
    """Extract metadata from a recipe's caption and populate the override."""
    from .caption_parser import parse_caption
    from .recipe_state_repository import fill_recipe_override

    with factory() as session:
        recipe = session.get(Recipe, recipe_id)
        if recipe is None:
            return None
        caption = recipe.caption

    fields = parse_caption(caption).as_override()
    if not fields:
        return None
    return fill_recipe_override(factory, recipe_id, fields)


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
    # Capture IDs before session operations expire mapped attrs
    ids = [r.id for r in recipes]
    for recipe in recipes:
        _promote_instagram_attrs(recipe)
    imported = insert_missing_recipes(factory, recipes)
    store_missing_photos(factory, recipes)
    if imported > 0:
        for recipe_id in ids:
            try:
                populate_recipe_from_caption(factory, recipe_id)
            except Exception as error:
                print(
                    f"Caption parsing skipped for {recipe_id}: {type(error).__name__}",
                    file=sys.stderr,
                )
    return imported


def import_post_by_url(
    root: Path, factory: sessionmaker[Session], url: str
) -> tuple[str, str, str, str] | None:
    """Scrape a specific Instagram post URL and store it in the database.

    Returns ``(shortcode, instagram_username, display_name, image_url)`` on success, or
    None if the URL is not a recognised Instagram post/reel path, the browser
    session is missing, or scraping fails.  Both ``instagram_username`` and
    ``display_name`` are empty strings when they could not be extracted.
    """

    match = _INSTAGRAM_MEDIA_RE.search(url)
    if not match:
        return None
    media_path = match.group(1).replace("/reels/", "/reel/").rstrip("/") + "/"

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
    image_url = recipe.image_url
    inserted = insert_missing_recipes(factory, [recipe])
    if inserted:
        store_missing_photos(factory, [recipe])
    else:
        with session_scope(factory) as session:
            existing = session.get(Recipe, shortcode)
            if existing is not None:
                existing.image_url = recipe.image_url
                existing.caption = recipe.caption
                existing.timestamp_utc = recipe.timestamp_utc
                existing.source = recipe.source
                existing.source_name = recipe.source_name
                existing.added_via = "instagram"
                if existing.post is not None and recipe.post is not None:
                    existing.post.url = recipe.post.url
                    existing.post.typename = recipe.post.typename
                    existing.post.is_video = recipe.post.is_video
                    existing.post.is_recipe = True

        photo_bytes = getattr(recipe, "_photo_bytes", None)
        photo_content_type = getattr(recipe, "_photo_content_type", "image/jpeg")
        if photo_bytes is None:
            photo = download_photo(recipe)
            if photo is not None:
                photo_bytes, photo_content_type = photo
        if photo_bytes is not None:
            replace_recipe_photo(factory, shortcode, photo_content_type, photo_bytes)
    return shortcode, source, source_name, image_url


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
