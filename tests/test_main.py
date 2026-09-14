"""Tests for cookbook report assembly."""

from __future__ import annotations

import json
from dataclasses import asdict

from cookbook.config import AppConfig
from cookbook.main import _fetch_posts_with_fallback

from cookbook.post_store_import import load_post_store
from cookbook.models import PostItem


def _post(shortcode: str, timestamp: str) -> PostItem:
    return PostItem(
        shortcode=shortcode,
        url="https://example.com",
        image_url="",
        caption="",
        timestamp_utc=timestamp,
        likes=0,
        comments=0,
        typename="GraphImage",
        is_video=False,
    )


def test_load_post_store_reads_complete_posts(tmp_path) -> None:
    store = tmp_path / "items"
    store.mkdir()
    newest = _post("alphabetically-first", "2026-01-02T00:00:00+00:00")
    oldest = _post("alphabetically-last", "2026-01-01T00:00:00+00:00")
    for post in (newest, oldest):
        (store / f"{post.shortcode}.json").write_text(
            json.dumps(asdict(post)), encoding="utf-8"
        )

    assert load_post_store(store) == [newest, oldest]


def test_configured_browser_scraper_is_used_without_calling_the_api(monkeypatch) -> None:
    config = AppConfig(
        username="example",
        limit=1,
        output="posts.json",
        reverse=False,
        login_user="user",
        session_file="session",
        env_file=".env",
        request_delay_seconds=0,
        max_fetch_attempts=1,
        retry_wait_seconds=1,
        use_browser=True,
        api_401_cooldown_hours=24,
        ignore_cached_posts=False,
        feed_position_from_end=1,
    )
    expected = [_post("browser-post", "2026-01-01T00:00:00+00:00")]
    monkeypatch.setattr("cookbook.main._fetch_posts_browser_only", lambda *_: expected)
    monkeypatch.setattr(
        "cookbook.main.fetch_posts_api",
        lambda *_: (_ for _ in ()).throw(AssertionError("API must not be called")),
    )

    assert _fetch_posts_with_fallback(config, "user", "password", set()) == expected
