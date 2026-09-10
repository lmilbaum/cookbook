"""Tests for post selection during browser scraping."""

from __future__ import annotations

from cookbook.browser_scraper import _select_unseen_media_paths


def test_select_position_from_end_uses_only_unseen_posts() -> None:
    paths = ["/p/old/", "/p/known/", "/p/new/", "/p/newest/"]

    assert _select_unseen_media_paths(paths, {"known", "newest"}, 1) == ["/p/new/"]
    assert _select_unseen_media_paths(paths, {"known", "newest"}, 2) == ["/p/old/"]


def test_select_position_from_end_returns_empty_when_unseen_position_is_missing() -> None:
    assert _select_unseen_media_paths(["/p/known/"], {"known"}, 1) == []
