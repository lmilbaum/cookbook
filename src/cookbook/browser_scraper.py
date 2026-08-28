# pylint: disable=line-too-long,too-many-locals,too-many-arguments,too-many-positional-arguments,too-many-branches,too-many-statements
"""Browser-based Instagram scraper using Playwright to bypass API rate limiting."""

from __future__ import annotations

import importlib
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import PostItem


def _normalize_instagram_image_url(image_url: str) -> str:
    """Remove crop/size query options so the CDN can serve a fuller image."""

    if not image_url:
        return image_url

    parsed = urlsplit(image_url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_pairs = [(key, value) for key, value in query_pairs if key != "stp"]
    normalized_query = urlencode(filtered_pairs)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, normalized_query, parsed.fragment))


def _extract_highest_resolution_image(page: Any) -> str:
    """Pick the highest-resolution image URL from article image candidates."""

    image_nodes: list[dict[str, str]] = page.locator("article img").evaluate_all(
        """
        elements => elements.map((img) => ({
            src: img.getAttribute('src') || '',
            currentSrc: img.currentSrc || '',
            srcset: img.getAttribute('srcset') || ''
        }))
        """
    )

    best_url = ""
    best_width = -1

    def consider_candidate(candidate_url: str, width_hint: int) -> None:
        nonlocal best_url, best_width
        if not candidate_url:
            return
        if width_hint > best_width:
            best_url = candidate_url
            best_width = width_hint

    for node in image_nodes:
        srcset = node.get("srcset", "")
        if srcset:
            for entry in srcset.split(","):
                trimmed = entry.strip()
                if not trimmed:
                    continue
                parts = trimmed.rsplit(" ", maxsplit=1)
                url = parts[0]
                width_hint = 0
                if len(parts) == 2:
                    width_match = re.match(r"^(\d+)w$", parts[1])
                    if width_match:
                        width_hint = int(width_match.group(1))
                consider_candidate(url, width_hint)

        consider_candidate(node.get("currentSrc", ""), 0)
        consider_candidate(node.get("src", ""), 0)

    return best_url


def _load_playwright() -> Any:
    """Import playwright with a user-facing dependency error."""

    try:
        return importlib.import_module("playwright.sync_api")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing dependency 'playwright'. Install dependencies with `uv sync`."
        ) from exc


def _browser_session_path(session_file: str) -> Path:
    """Keep Playwright session state separate from Instaloader session files."""

    path = Path(session_file)
    if path.suffix == ".json":
        return path
    return path.with_name(f"{path.name}.browser.json")


def _dismiss_login_prompts(page: Any) -> None:
    """Dismiss common Instagram prompts that appear after login."""

    for label in ("Not now", "Not Now", "Save info", "Save Info"):
        button = page.get_by_role("button", name=label)
        if button.count() > 0:
            button.first.click(timeout=3000)
            time.sleep(1)


def _fill_first_available(
    page: Any, selectors: tuple[str, ...], value: str, field_name: str
) -> None:
    """Fill the first matching field from a list of candidate selectors."""

    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() > 0:
            locator.fill(value)
            return
    raise RuntimeError(f"Could not find Instagram {field_name} field.")


def _context_has_session(context: Any) -> bool:
    """Check whether the browser context currently holds an Instagram session cookie."""

    cookies = context.cookies()
    return any(cookie.get("name") == "sessionid" for cookie in cookies)


def _profile_requires_login(page: Any) -> bool:
    """Detect whether Instagram is still showing an unauthenticated surface."""

    current_url = page.url.lower()
    if "/accounts/login" in current_url or "/challenge/" in current_url:
        return True

    body_text = page.locator("body").inner_text(timeout=5000).lower()
    return any(
        marker in body_text
        for marker in ("log in", "login", "sign up", "challenge_required")
    )


def _open_profile(page: Any, username: str, timeout_seconds: int) -> None:
    """Navigate to the requested Instagram profile."""

    profile_url = f"https://www.instagram.com/{username}/"
    page.goto(profile_url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
    time.sleep(3)


def _verify_profile_access(page: Any, username: str, timeout_seconds: int) -> bool:
    """Confirm the current context can access the target profile while authenticated."""

    _open_profile(page, username, timeout_seconds)
    return not _profile_requires_login(page)


def _login_instagram(page: Any, username: str, password: str, timeout_seconds: int) -> None:
    """Log in to Instagram using the web UI."""

    print(f"Attempting to login as {username}...")
    page.goto(
        "https://www.instagram.com/accounts/login/",
        wait_until="domcontentloaded",
        timeout=timeout_seconds * 1000,
    )
    time.sleep(3)

    _fill_first_available(
        page,
        (
            'input[name="username"]',
            'input[name="email"]',
            'input[aria-label="Phone number, username, or email"]',
            'input[autocomplete*="username"]',
        ),
        username,
        "username",
    )
    _fill_first_available(
        page,
        (
            'input[name="password"]',
            'input[name="pass"]',
            'input[aria-label="Password"]',
            'input[autocomplete="current-password"]',
        ),
        password,
        "password",
    )

    page.locator('input[name="password"], input[name="pass"]').first.press("Enter")

    page.wait_for_load_state("domcontentloaded", timeout=timeout_seconds * 1000)
    time.sleep(5)
    _dismiss_login_prompts(page)


def _extract_media_paths(page: Any, username: str) -> list[str]:
    """Extract unique post and reel paths for the requested profile."""

    hrefs: list[str] = page.locator('a[href*="/p/"], a[href*="/reel/"]').evaluate_all(
        "elements => elements.map((element) => element.getAttribute('href') || '')"
    )

    media_paths: list[str] = []
    seen: set[str] = set()
    patterns = (
        rf"^/{re.escape(username)}/(p|reel)/([^/]+)/",
        r"^/(p|reel)/([^/]+)/",
    )
    for href in hrefs:
        normalized = ""
        for pattern in patterns:
            match = re.search(pattern, href)
            if not match:
                continue
            if len(match.groups()) == 2:
                normalized = f"/{match.group(1)}/{match.group(2)}/"
            else:
                normalized = f"/{match.group(2)}/{match.group(3)}/"
            break
        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        media_paths.append(normalized)

    return media_paths


def _merge_media_paths(
    all_media_paths: list[str], current_media_paths: list[str], seen: set[str]
) -> int:
    """Merge newly discovered media into the accumulated crawl result."""

    new_items = 0
    for media_path in current_media_paths:
        if media_path in seen:
            continue

        seen.add(media_path)
        all_media_paths.append(media_path)
        new_items += 1

    return new_items


def _scroll_profile_until_complete(page: Any, username: str) -> list[str]:
    """Scroll the profile until no new media items are loaded."""

    max_scrolls = 4000
    target_media_items = 3000
    checkpoint_size = 3000
    idle_scroll_limit = 18

    all_media_paths: list[str] = []
    seen: set[str] = set()
    idle_scrolls = 0
    next_checkpoint = checkpoint_size
    slow_recheck_done = False

    initial_paths = _extract_media_paths(page, username)
    _merge_media_paths(all_media_paths, initial_paths, seen)

    for scroll_index in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.12)
        page.evaluate("window.scrollBy(0, 2600)")
        time.sleep(0.08)

        current_paths = _extract_media_paths(page, username)
        new_items = _merge_media_paths(all_media_paths, current_paths, seen)
        if new_items == 0:
            # Fallback to a slower pass before counting idle, to allow lazy loads.
            page.evaluate("window.scrollBy(0, 1800)")
            time.sleep(0.35)
            retry_paths = _extract_media_paths(page, username)
            new_items = _merge_media_paths(all_media_paths, retry_paths, seen)
        print(
            f"  Scrolled {scroll_index + 1} time(s)... "
            f"{len(all_media_paths)} total media items"
        )

        while len(all_media_paths) >= next_checkpoint:
            print(f"  Reached {next_checkpoint} media items")
            next_checkpoint += checkpoint_size

        if len(all_media_paths) >= target_media_items:
            print(f"  Reached target of {target_media_items} media items")
            break

        if new_items == 0:
            idle_scrolls += 1
        else:
            idle_scrolls = 0

        if idle_scrolls >= idle_scroll_limit:
            if slow_recheck_done:
                break

            # One slow verification cycle avoids false "end reached" at high speed.
            slow_recheck_done = True
            recovered = 0
            for _ in range(8):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(0.45)
                page.evaluate("window.scrollBy(0, 1200)")
                time.sleep(0.25)
                recovered += _merge_media_paths(
                    all_media_paths,
                    _extract_media_paths(page, username),
                    seen,
                )

            if recovered > 0:
                print(f"  Slow recheck recovered {recovered} media items")
                idle_scrolls = 0

    return all_media_paths


def _shortcode_from_media_path(media_path: str) -> str:
    """Extract the stable post shortcode from a profile media path."""

    shortcode_match = re.search(r"^/(?:p|reel)/([^/]+)/$", media_path)
    return shortcode_match.group(1) if shortcode_match else media_path.strip("/")


def _extract_caption(page: Any) -> str:
    """Extract a caption from the article, with metadata fallback."""

    article = page.locator("article").first
    if article.count() > 0:
        caption = article.inner_text(timeout=5000).strip()
        if caption:
            return caption

    for selector in ('meta[property="og:description"]', 'meta[name="description"]'):
        metadata = page.locator(selector).first
        if metadata.count() > 0:
            caption = (metadata.get_attribute("content") or "").strip()
            if caption:
                return caption
    return ""


def _fetch_post_details(page: Any, media_path: str, timeout_seconds: int) -> PostItem:
    """Fetch details for a single post or reel by navigating to its page."""

    post_url = f"https://www.instagram.com{media_path}"
    page.goto(post_url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
    time.sleep(2)

    timestamp_utc = datetime.now(UTC).isoformat()
    time_locator = page.locator("time").first
    if time_locator.count() > 0:
        timestamp_raw = time_locator.get_attribute("datetime")
        if timestamp_raw is not None:
            try:
                timestamp_utc = datetime.fromisoformat(timestamp_raw).astimezone(UTC).isoformat()
            except ValueError:
                pass

    page_text = page.locator("body").inner_text(timeout=5000)
    like_match = re.search(r"(\d+)\s+likes?", page_text, flags=re.IGNORECASE)
    comment_match = re.search(r"(\d+)\s+comments?", page_text, flags=re.IGNORECASE)

    caption = _extract_caption(page)

    image_url = _extract_highest_resolution_image(page)
    if not image_url:
        image_meta = page.locator('meta[property="og:image"]').first
        if image_meta.count() > 0:
            image_url = image_meta.get_attribute("content") or ""
    image_url = _normalize_instagram_image_url(image_url)

    shortcode = _shortcode_from_media_path(media_path)
    is_video = media_path.startswith("/reel/")

    return PostItem(
        shortcode=shortcode,
        url=post_url,
        image_url=image_url,
        caption=caption,
        timestamp_utc=timestamp_utc,
        likes=int(like_match.group(1)) if like_match else 0,
        comments=int(comment_match.group(1)) if comment_match else 0,
        typename="GraphVideo" if is_video else "GraphImage",
        is_video=is_video,
    )


def _new_context(browser: Any, session_state: Path | None, block_media: bool = False) -> Any:
    """Create a Playwright browser context with stable defaults."""

    context_options: dict[str, Any] = {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1440, "height": 1200},
    }
    if session_state is not None and session_state.exists():
        context_options["storage_state"] = str(session_state)

    context = browser.new_context(**context_options)
    if block_media:
        def _route_handler(route: Any) -> None:
            if route.request.resource_type in {"image", "media", "font"}:
                route.abort()
                return
            route.continue_()

        context.route("**/*", _route_handler)
    return context


def fetch_posts_browser(
    username: str,
    limit: int = 0,
    headless: bool = True,
    timeout_seconds: int = 30,
    login_user: str = "",
    login_pass: str = "",
    reverse: bool = False,
    session_file: str = ".instagram.session",
    seen_shortcodes: set[str] | None = None,
    feed_position_from_end: int = 0,
) -> list[PostItem]:
    """Fetch Instagram posts using a headless browser with required authentication."""

    if not login_user:
        raise ValueError("Browser scraping requires INSTAGRAM_USERNAME or login_user.")
    if not login_pass:
        raise ValueError("Browser scraping requires INSTAGRAM_PASSWORD.")

    playwright = _load_playwright()
    browser_session = _browser_session_path(session_file)
    seen_shortcodes = seen_shortcodes or set()

    with playwright.sync_playwright() as playwright_driver:
        browser = playwright_driver.chromium.launch(headless=headless)
        crawl_context = _new_context(browser, browser_session, block_media=True)
        page = crawl_context.new_page()

        detail_context: Any | None = None
        try:
            authenticated = False
            if browser_session.exists() and _context_has_session(crawl_context):
                authenticated = _verify_profile_access(page, username, timeout_seconds)
                if authenticated:
                    print(f"Reused browser session from {browser_session}")

            if not authenticated:
                crawl_context.close()
                crawl_context = _new_context(browser, None, block_media=True)
                page = crawl_context.new_page()
                _login_instagram(page, login_user, login_pass, timeout_seconds)
                authenticated = _context_has_session(crawl_context) and _verify_profile_access(
                    page, username, timeout_seconds
                )
                if not authenticated:
                    raise RuntimeError(
                        "Instagram browser login failed. Credentials may be rejected or a verification challenge is required."
                    )
                browser_session.parent.mkdir(parents=True, exist_ok=True)
                crawl_context.storage_state(path=str(browser_session))
                print(f"Saved browser session to {browser_session}")

            _open_profile(page, username, timeout_seconds)

            print("Scrolling to load posts...")
            media_paths = _scroll_profile_until_complete(page, username)
            print(f"Collected {len(media_paths)} media items from the profile grid")

            if not media_paths:
                raise RuntimeError(
                    f"No posts found on profile {username}. The profile may be private or Instagram changed the page structure."
                )

            if reverse:
                media_paths.reverse()

            if feed_position_from_end > 0:
                position = len(media_paths) - feed_position_from_end
                media_paths = [media_paths[position]] if position >= 0 else []

            media_paths = [
                media_path
                for media_path in media_paths
                if _shortcode_from_media_path(media_path) not in seen_shortcodes
            ]

            if limit > 0:
                media_paths = media_paths[:limit]

            if not media_paths:
                print(f"No unseen posts found for profile {username}")
                return []

            print(f"Fetching details for {len(media_paths)} media items...")
            crawl_context.storage_state(path=str(browser_session))
            crawl_context.close()

            detail_context = _new_context(browser, browser_session, block_media=False)
            detail_page = detail_context.new_page()

            posts: list[PostItem] = []
            for index, media_path in enumerate(media_paths, start=1):
                posts.append(_fetch_post_details(detail_page, media_path, timeout_seconds))
                print(f"  [{index}] Fetched media {media_path}")
                time.sleep(0.6)

            if not posts:
                raise RuntimeError(f"Failed to extract post details from profile {username}.")

            print(f"Successfully extracted {len(posts)} posts")
            return posts
        finally:
            if detail_context is not None:
                detail_context.close()
            crawl_context.close()
            browser.close()
