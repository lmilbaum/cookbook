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
from .models import PostRecord
from .report_html import (
    render_html,
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


def _prune_cached_assets(posts: list[PostRecord], output_path: Path) -> None:
    """Remove cached assets that are not part of the current report."""

    assets_dir = output_path.with_name(f"{output_path.stem}_assets")
    if not assets_dir.exists():
        return

    keep_shortcodes = {post.shortcode for post in posts}
    for asset_path in assets_dir.iterdir():
        if not asset_path.is_file():
            continue
        if asset_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        if asset_path.stem not in keep_shortcodes:
            asset_path.unlink()


# pylint: disable=too-many-locals
def _cache_images_for_report(
    posts: list[PostRecord],
    output_path: Path,
    reuse_cached_assets: bool = True,
) -> list[PostRecord]:
    """Download image URLs to local files for robust HTML rendering."""

    assets_dir = output_path.with_name(f"{output_path.stem}_assets")
    assets_dir.mkdir(parents=True, exist_ok=True)

    cached_posts: list[PostRecord] = []
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


def _seen_posts_path(output_path: Path) -> Path:
    """Return the sidecar path used to track processed posts."""

    return output_path.with_name(f"{output_path.stem}.seen.json")


def _post_store_path(output_path: Path) -> Path:
    """Return the write-once directory used as the post source of truth."""

    return output_path.with_name(f"{output_path.stem}_records")


def _titles_path(output_path: Path) -> Path:
    """Return the sidecar path containing user-authored post titles."""

    return output_path.with_name(f"{output_path.stem}_titles.json")


def _load_titles(titles_path: Path) -> dict[str, str]:
    """Load user-authored titles keyed by post shortcode."""

    if not titles_path.exists():
        return {}

    try:
        payload = json.loads(titles_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid post titles file: {titles_path}") from exc

    if not isinstance(payload, dict) or not all(
        isinstance(shortcode, str) and isinstance(title, str)
        for shortcode, title in payload.items()
    ):
        raise ValueError(
            f"Post titles file must contain a shortcode-to-title object: {titles_path}"
        )
    return payload


def _load_post_store(store_path: Path) -> list[PostRecord]:
    """Load all valid post records from the immutable per-post store."""

    if not store_path.exists():
        return []

    posts: list[PostRecord] = []
    for record_path in sorted(store_path.glob("*.json")):
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            posts.append(PostRecord(**payload))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Invalid post record: {record_path}") from exc
    return posts


def _write_post_records(store_path: Path, posts: list[PostRecord]) -> None:
    """Write new post records without ever replacing existing records."""

    store_path.mkdir(parents=True, exist_ok=True)
    for post in posts:
        record_path = store_path / f"{post.shortcode}.json"
        if record_path.exists():
            continue

        temporary_path = store_path / f".{post.shortcode}.json.tmp"
        temporary_path.write_text(
            json.dumps(asdict(post), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(record_path)


def _migrate_titles_to_post_records(store_path: Path, titles: dict[str, str]) -> None:
    """Copy legacy sidecar titles into the corresponding post records."""

    for shortcode, title in titles.items():
        title = title.strip()
        record_path = store_path / f"{shortcode}.json"
        if not title or not record_path.exists():
            continue

        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid post record: {record_path}") from exc
        if payload.get("title", "").strip() == title:
            continue

        payload["title"] = title
        temporary_path = record_path.with_name(f".{record_path.name}.tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(record_path)


def _apply_titles(posts: list[PostRecord], titles: dict[str, str]) -> list[PostRecord]:
    """Apply legacy sidecar titles to newly fetched records."""

    return [
        replace(post, title=titles.get(post.shortcode, post.title).strip())
        for post in posts
    ]


def _load_seen_shortcodes(seen_path: Path, output_path: Path) -> set[str]:
    """Load processed shortcodes, bootstrapping from existing output if needed."""

    source_path = seen_path if seen_path.exists() else output_path
    if not source_path.exists():
        return set()

    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"Failed to read processed-post data: {source_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in processed-post data: {source_path}") from exc

    if source_path == seen_path:
        if not isinstance(payload, list) or not all(
            isinstance(shortcode, str) and shortcode for shortcode in payload
        ):
            raise ValueError(f"Processed-post sidecar must contain a list of strings: {seen_path}")
        return set(payload)

    if not isinstance(payload, list):
        raise TypeError(f"Existing output must contain a list of posts: {output_path}")

    shortcodes: set[str] = set()
    for post in payload:
        if not isinstance(post, dict):
            raise TypeError(f"Existing output contains an invalid post: {output_path}")
        shortcode = post.get("shortcode")
        if not isinstance(shortcode, str) or not shortcode:
            raise ValueError(f"Existing output contains a post without a shortcode: {output_path}")
        shortcodes.add(shortcode)
    return shortcodes


def _write_seen_shortcodes(seen_path: Path, shortcodes: set[str]) -> None:
    """Atomically persist processed shortcodes."""

    seen_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = seen_path.with_name(f".{seen_path.name}.tmp")
    temporary_path.write_text(
        json.dumps(sorted(shortcodes), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(seen_path)


def _load_existing_posts(output_path: Path) -> list[PostRecord]:
    """Load previously exported posts so reports keep history."""

    if not output_path.exists():
        return []

    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"Failed to read existing output: {output_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in existing output: {output_path}") from exc

    if not isinstance(payload, list):
        raise TypeError(f"Existing output must contain a list of posts: {output_path}")

    posts: list[PostRecord] = []
    for post in payload:
        if not isinstance(post, dict):
            raise TypeError(f"Existing output contains an invalid post: {output_path}")
        try:
            posts.append(PostRecord(**post))
        except TypeError as exc:
            raise ValueError(
                f"Existing output contains malformed post fields: {output_path}"
            ) from exc
    return posts


def _merge_posts(
    existing_posts: list[PostRecord],
    new_posts: list[PostRecord],
    reverse: bool,
) -> list[PostRecord]:
    """Merge old and new posts by shortcode while preserving configured ordering."""

    merged: list[PostRecord] = []
    seen_shortcodes: set[str] = set()
    ordered_posts = (existing_posts + new_posts) if reverse else (new_posts + existing_posts)

    for post in ordered_posts:
        if post.shortcode in seen_shortcodes:
            continue
        seen_shortcodes.add(post.shortcode)
        merged.append(post)
    return merged


def _fetch_posts_browser_only(
    config: AppConfig,
    login_user: str,
    password: str,
    seen_shortcodes: set[str],
) -> list[PostRecord]:
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
) -> list[PostRecord]:
    """Try API first, then fall back to browser scraping on unauthorized response."""

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

    if config.limit < 0:
        raise ValueError("Config key 'limit' must be >= 0.")

    base_dir = config_path.parent.resolve()
    env_path = resolve_from(base_dir, config.env_file)
    session_path = resolve_from(base_dir, config.session_file)
    output_path = resolve_from(base_dir, config.output)
    seen_path = _seen_posts_path(output_path)
    store_path = _post_store_path(output_path)
    titles_path = _titles_path(output_path)

    load_dotenv = load_dotenv_loader()
    load_dotenv(env_path)

    login_user = config.login_user or os.getenv("INSTAGRAM_USERNAME", "").strip()
    password = os.getenv("INSTAGRAM_PASSWORD", "").strip()
    config.session_file = str(session_path)

    seen_shortcodes = _load_seen_shortcodes(seen_path, output_path)
    titles = _load_titles(titles_path)
    fetch_seen_shortcodes = set() if config.ignore_cached_posts else seen_shortcodes
    existing_posts: list[PostRecord] = []
    if not config.ignore_cached_posts:
        _migrate_titles_to_post_records(store_path, titles)
        existing_posts = _load_post_store(store_path)
        if not existing_posts and output_path.exists():
            existing_posts = _load_existing_posts(output_path)
            _write_post_records(store_path, existing_posts)
        fetch_seen_shortcodes |= {post.shortcode for post in existing_posts}
        if config.feed_position_from_end > 0:
            fetch_seen_shortcodes = {post.shortcode for post in existing_posts}

    fetch_config = config
    should_fetch = True
    if not config.ignore_cached_posts and config.limit > 0:
        remaining_slots = max(config.limit - len(existing_posts), 0)
        should_fetch = remaining_slots > 0
        if should_fetch:
            fetch_config = replace(config, limit=remaining_slots)

    new_posts = (
        _fetch_posts_with_fallback(fetch_config, login_user, password, fetch_seen_shortcodes)
        if should_fetch
        else []
    )
    new_posts = _apply_titles(new_posts, titles)
    if not config.ignore_cached_posts:
        _write_post_records(store_path, new_posts)
    merged_posts = new_posts if config.ignore_cached_posts else _merge_posts(
        existing_posts,
        new_posts,
        config.reverse,
    )
    if not config.ignore_cached_posts and config.limit > 0:
        merged_posts = merged_posts[:config.limit]

    report_posts = _cache_images_for_report(
        merged_posts,
        output_path,
        reuse_cached_assets=not config.ignore_cached_posts,
    )
    if config.ignore_cached_posts:
        _prune_cached_assets(report_posts, output_path)

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
            titles=titles,
        ),
        encoding="utf-8",
    )
    shopping_list_path = html_path.with_name("shopping_list.html")
    shopping_list_path.write_text(
        render_shopping_list_html(favicon_href=favicon_path.name),
        encoding="utf-8",
    )
    if not config.ignore_cached_posts:
        _write_seen_shortcodes(
            seen_path,
            seen_shortcodes | {post.shortcode for post in merged_posts},
        )

    was_opened = webbrowser.open(html_path.resolve().as_uri())
    if not was_opened:
        raise RuntimeError(f"Failed to open HTML report: {html_path}")

    print(f"Fetched {len(new_posts)} new posts for @{config.username} -> {output_path}")
    print(f"Total posts in output: {len(merged_posts)}")
    print(f"Updated and opened HTML report -> {html_path}")
    if config.ignore_cached_posts:
        print("Skipped processed-post sidecar update (strict window mode)")
    else:
        print(f"Updated processed-post sidecar -> {seen_path}")


if __name__ == "__main__":
    main()
