"""Tests for post selection during browser scraping."""

from __future__ import annotations

from datetime import UTC, datetime

from cookbook.browser_scraper import _fetch_post_details, _select_unseen_media_paths


def test_select_position_from_end_uses_only_unseen_posts() -> None:
    paths = ["/p/old/", "/p/known/", "/p/new/", "/p/newest/"]

    assert _select_unseen_media_paths(paths, {"known", "newest"}, 1) == ["/p/new/"]
    assert _select_unseen_media_paths(paths, {"known", "newest"}, 2) == ["/p/old/"]


def test_select_position_from_end_returns_empty_when_unseen_position_is_missing() -> None:
    assert _select_unseen_media_paths(["/p/known/"], {"known"}, 1) == []


def test_scroll_continues_past_3000_posts(monkeypatch):
    from cookbook import browser_scraper as scraper
    pages = iter([
        [f'/p/post-{index}/' for index in range(3000)],
        ['/p/older/'],
        ['/p/oldest/'],
    ])
    monkeypatch.setattr(scraper, '_extract_media_paths', lambda *_: next(pages, ['/p/oldest/']))
    monkeypatch.setattr(scraper.time, 'sleep', lambda _: None)
    class Page:
        def evaluate(self, _script): pass
    paths = scraper._scroll_profile_until_complete(Page(), 'example')
    assert len(paths) == 3002
    assert scraper._select_unseen_media_paths(paths, set(), 1) == ['/p/oldest/']


def test_scroll_limit_never_returns_a_partial_feed(monkeypatch):
    import pytest

    from cookbook import browser_scraper as scraper
    sequence = iter(range(5000))
    monkeypatch.setattr(scraper, '_extract_media_paths', lambda *_: [f'/p/post-{next(sequence)}/'])
    monkeypatch.setattr(scraper.time, 'sleep', lambda _: None)
    class Page:
        def evaluate(self, _script): pass
    with pytest.raises(RuntimeError, match='before finding the feed end'):
        scraper._scroll_profile_until_complete(Page(), 'example')


def test_oldest_unimported_uses_newest_first_profile_order():
    paths = ['/p/newest/', '/p/middle/', '/p/oldest/']
    assert _select_unseen_media_paths(paths, set(), 1) == ['/p/oldest/']
    assert _select_unseen_media_paths(paths, {'oldest'}, 1) == ['/p/middle/']


def test_known_publication_time_overrides_unreliable_reel_dom_time(page):
    # Reels commonly lack a <time> element carrying the true publish date;
    # the confirmed profile-timeline timestamp must win over any DOM guess.
    page.route('https://www.instagram.com/reel/known/', lambda route: route.fulfill(
        content_type='text/html',
        body='<article>caption</article><time datetime="2026-09-14T00:00:00Z"></time>'))
    taken_at = int(datetime(2022, 8, 11, tzinfo=UTC).timestamp())
    post = _fetch_post_details(page, '/reel/known/', timeout_seconds=5, taken_at=taken_at)
    assert post.timestamp_utc == datetime.fromtimestamp(taken_at, UTC).isoformat()


def test_missing_publication_time_falls_back_to_dom_time(page):
    page.route('https://www.instagram.com/p/known/', lambda route: route.fulfill(
        content_type='text/html',
        body='<article>caption</article><time datetime="2022-08-11T00:00:00Z"></time>'))
    post = _fetch_post_details(page, '/p/known/', timeout_seconds=5)
    assert post.timestamp_utc == datetime(2022, 8, 11, tzinfo=UTC).isoformat()
