"""Fetch Instagram profile posts and export them to JSON and HTML."""

from __future__ import annotations

import json
import os
import webbrowser
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .api_method import InstagramUnauthorizedError, fetch_posts_api
from .browser_scraper import fetch_posts_browser
from .config import AppConfig, load_config, parse_args, resolve_from
from .dependencies import load_dotenv_loader
from .models import PostItem
from .database import create_session_factory
from .post_repository import insert_missing_posts, load_posts
from .report_html import (
    render_html,
    render_notes_html,
    render_shopping_list_html,
    write_favicon,
)


def _find_cached_asset(assets_dir: Path, shortcode: str) -> Path | None:
    """Return an existing cached asset path for a shortcode when present."""

    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = assets_dir / f"{shortcode}{suffix}"
        if candidate.exists():
            return candidate
    return None


# pylint: disable=too-many-locals
def _cache_images_for_report(
    posts: list[PostItem],
    output_path: Path,
    reuse_cached_assets: bool = True,
) -> list[PostItem]:
    """Download image URLs to local files for robust HTML rendering."""

    assets_dir = output_path.with_name(f"{output_path.stem}_assets")
    assets_dir.mkdir(parents=True, exist_ok=True)

    cached_posts: list[PostItem] = []
    for post in posts:
        image_url = post.image_url.strip()
        if not image_url.startswith("http"):
            cached_posts.append(post)
            continue

        existing_cached_asset = _find_cached_asset(assets_dir, post.shortcode)
        if reuse_cached_assets and existing_cached_asset is not None:
            local_ref = existing_cached_asset.relative_to(output_path.parent).as_posix()
            cached_posts.append(replace(post, image_url=local_ref))
            continue

        split = urlsplit(image_url)
        suffix = Path(split.path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"

        target_path = assets_dir / f"{post.shortcode}{suffix}"
        candidate_urls = [
            image_url,
            f"https://www.instagram.com/p/{post.shortcode}/media/?size=l",
            f"https://www.instagram.com/p/{post.shortcode}/media/?size=m",
        ]

        content: bytes | None = None
        for candidate_url in candidate_urls:
            try:
                request = Request(
                    candidate_url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    },
                )
                with urlopen(request, timeout=20) as response:
                    content = response.read()
                if content:
                    break
            except OSError:
                continue

        if content is None:
            fallback_asset = _find_cached_asset(assets_dir, post.shortcode)
            if fallback_asset is not None:
                local_ref = fallback_asset.relative_to(output_path.parent).as_posix()
                cached_posts.append(replace(post, image_url=local_ref))
            else:
                cached_posts.append(replace(post, image_url=""))
            continue

        target_path.write_bytes(content)
        local_ref = target_path.relative_to(output_path.parent).as_posix()
        cached_posts.append(replace(post, image_url=local_ref))

    return cached_posts


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
) -> list[PostItem]:
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
) -> list[PostItem]:
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
    output_path = resolve_from(base_dir, config.output)
    load_dotenv = load_dotenv_loader()
    load_dotenv(env_path)

    login_user = config.login_user or os.getenv("INSTAGRAM_USERNAME", "").strip()
    password = os.getenv("INSTAGRAM_PASSWORD", "").strip()
    config.session_file = str(session_path)

    session_factory = create_session_factory()
    fetch_seen_shortcodes: set[str] = set()
    existing_posts: list[PostItem] = []
    if not config.ignore_cached_posts:
        existing_posts = load_posts(session_factory, reverse=config.reverse)
        fetch_seen_shortcodes = {post.shortcode for post in existing_posts}
        if config.feed_position_from_end > 0:
            fetch_seen_shortcodes = {post.shortcode for post in existing_posts}

    fetch_config = config
    should_fetch = True
    if not config.ignore_cached_posts and config.limit > 0:
        if config.feed_position_from_end > 0:
            # A targeted position is a request for one candidate, independent
            # of how many posts have already been imported.
            fetch_config = replace(config, limit=1)
        else:
            remaining_slots = max(config.limit - len(existing_posts), 0)
            should_fetch = remaining_slots > 0
            if should_fetch:
                fetch_config = replace(config, limit=remaining_slots)

    new_posts = (
        _fetch_posts_with_fallback(fetch_config, login_user, password, fetch_seen_shortcodes)
        if should_fetch
        else []
    )
    if not config.ignore_cached_posts:
        insert_missing_posts(session_factory, new_posts)
        merged_posts = load_posts(session_factory, reverse=config.reverse)
    else:
        merged_posts = new_posts
    report_posts = _cache_images_for_report(
        merged_posts,
        output_path,
        reuse_cached_assets=not config.ignore_cached_posts,
    )

    payload = [asdict(post) for post in report_posts]
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    favicon_path = write_favicon(output_path)
    html_path = output_path.with_suffix(".html")
    html_path.write_text(
        render_html(
            report_posts,
            config.username,
            favicon_href=favicon_path.name,
        ),
        encoding="utf-8",
    )
    shopping_list_path = html_path.with_name("shopping_list.html")
    shopping_list_path.write_text(
        render_shopping_list_html(favicon_href=favicon_path.name),
        encoding="utf-8",
    )
    notes_path = html_path.with_name("notes.html")
    notes_path.write_text(
        render_notes_html(report_posts, favicon_href=favicon_path.name),
        encoding="utf-8",
    )
    if not args.no_open:
        was_opened = webbrowser.open(html_path.resolve().as_uri())
        if not was_opened:
            raise RuntimeError(f"Failed to open HTML report: {html_path}")

    print(f"Fetched {len(new_posts)} new posts for @{config.username} -> {output_path}")
    print(f"Total posts in output: {len(merged_posts)}")
    action = "Updated HTML report" if args.no_open else "Updated and opened HTML report"
    print(f"{action} -> {html_path}")
    if config.ignore_cached_posts:
        print("Skipped database writes (strict window mode)")
    else:
        print("Post source of truth: PostgreSQL")


if __name__ == "__main__":
    main()
