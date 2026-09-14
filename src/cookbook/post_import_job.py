"""Import one unseen post from the feed end, directly through the scraper."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .browser_scraper import IncompleteProfileError, fetch_posts_browser
from .config import load_config, resolve_from
from .database import create_session_factory
from .main import _cache_images_for_report
from .models import Post
from .post_repository import insert_missing_posts


def import_next_post(root: Path, factory: sessionmaker[Session]) -> int:
    """Skip every stored post, including hidden posts, and import one candidate."""
    config = load_config(root / "cookbook.toml")
    load_dotenv(resolve_from(root, config.env_file))
    with factory() as session:
        seen = set(session.scalars(select(Post.shortcode)))
    posts = fetch_posts_browser(
        config.username, limit=1, headless=True,
        login_user=config.login_user or os.getenv("INSTAGRAM_USERNAME", "").strip(),
        login_pass=os.getenv("INSTAGRAM_PASSWORD", "").strip(),
        session_file=str(resolve_from(root, config.session_file)),
        seen_shortcodes=seen, feed_position_from_end=1,
    )
    posts = [post for post in posts if post.shortcode not in seen][:1]
    if not posts:
        return 0
    _cache_images_for_report(posts, root / "lizapanelim_posts.json")
    return insert_missing_posts(factory, posts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    load_dotenv(root / ".env")
    try:
        imported = import_next_post(root, create_session_factory())
    except IncompleteProfileError:
        raise SystemExit(4) from None
    raise SystemExit(0 if imported else 3)


if __name__ == "__main__":
    main()
