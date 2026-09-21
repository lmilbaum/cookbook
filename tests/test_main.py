"""Tests for cookbook report assembly."""

from __future__ import annotations

import json

from cookbook.config import AppConfig
from cookbook.main import _fetch_posts_with_fallback
from cookbook.models import Post, Recipe
from cookbook.post_store_import import load_post_store


def _flat_post_payload(shortcode: str, timestamp: str) -> dict[str, object]:
    """Build a legacy flat per-post JSON payload, the on-disk store's format."""

    return {
        "shortcode": shortcode,
        "url": "https://example.com",
        "image_url": "",
        "caption": "",
        "timestamp_utc": timestamp,
        "likes": 0,
        "comments": 0,
        "typename": "GraphImage",
        "is_video": False,
        "title": "",
        "recipe_url": "",
        "recipe_urls": [],
        "recipe_names": [],
    }


def _recipe(shortcode: str, timestamp: str) -> Recipe:
    recipe = Recipe(id=shortcode, image_url="", caption="", timestamp_utc=timestamp)
    recipe.post = Post(shortcode=shortcode, url="https://example.com", typename="GraphImage", is_video=False)
    return recipe


def test_load_post_store_reads_complete_posts(tmp_path) -> None:
    store = tmp_path / "items"
    store.mkdir()
    newest = _flat_post_payload("alphabetically-first", "2026-01-02T00:00:00+00:00")
    oldest = _flat_post_payload("alphabetically-last", "2026-01-01T00:00:00+00:00")
    for payload in (newest, oldest):
        (store / f"{payload['shortcode']}.json").write_text(json.dumps(payload), encoding="utf-8")

    assert load_post_store(store) == [
        _recipe("alphabetically-first", "2026-01-02T00:00:00+00:00"),
        _recipe("alphabetically-last", "2026-01-01T00:00:00+00:00"),
    ]


def test_configured_browser_scraper_is_used_without_calling_the_api(monkeypatch) -> None:
    config = AppConfig(
        username="example",
        limit=1,
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
    expected = [_recipe("browser-post", "2026-01-01T00:00:00+00:00")]
    monkeypatch.setattr("cookbook.main._fetch_posts_browser_only", lambda *_: expected)
    monkeypatch.setattr(
        "cookbook.main.fetch_posts_api",
        lambda *_: (_ for _ in ()).throw(AssertionError("API must not be called")),
    )

    assert _fetch_posts_with_fallback(config, "user", "password", set()) == expected
