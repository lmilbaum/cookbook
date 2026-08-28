"""Tests for cookbook report assembly."""

from __future__ import annotations

import json
from dataclasses import asdict

from cookbook.main import _load_post_store
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


def test_load_post_store_uses_configured_chronological_order(tmp_path) -> None:
    store = tmp_path / "items"
    store.mkdir()
    newest = _post("alphabetically-first", "2026-01-02T00:00:00+00:00")
    oldest = _post("alphabetically-last", "2026-01-01T00:00:00+00:00")
    for post in (newest, oldest):
        (store / f"{post.shortcode}.json").write_text(
            json.dumps(asdict(post)), encoding="utf-8"
        )

    assert [post.shortcode for post in _load_post_store(store, reverse=True)] == [
        oldest.shortcode,
        newest.shortcode,
    ]
    assert [post.shortcode for post in _load_post_store(store, reverse=False)] == [
        newest.shortcode,
        oldest.shortcode,
    ]
