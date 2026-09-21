"""Import one unseen post from the feed end, directly through the scraper."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .browser_scraper import IncompleteProfileError, fetch_posts_browser
from .config import load_config, resolve_from
from .database import create_session_factory
from .import_service import REASON_PREFIX
from .models import Post
from .post_repository import insert_missing_recipes
from .recipe_photo_fetch import store_missing_photos


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
    imported = insert_missing_recipes(factory, recipes)
    store_missing_photos(factory, recipes)
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    load_dotenv(root / ".env")
    try:
        imported = import_next_post(root, create_session_factory())
    except IncompleteProfileError as error:
        print(f"{REASON_PREFIX}{error}", file=sys.stderr)
        raise SystemExit(4) from None
    raise SystemExit(0 if imported else 3)


if __name__ == "__main__":
    main()
