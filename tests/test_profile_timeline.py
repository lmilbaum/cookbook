"""Profile timestamps and pagination, not discovered link order, select oldest posts."""
from __future__ import annotations

import pytest

from cookbook.browser_scraper import (
    IncompleteProfileError,
    _scroll_profile_until_complete,
    _select_unseen_media_paths,
)
from cookbook.profile_timeline import ProfileTimeline


def payload(nodes, more):
    return {'data': {ProfileTimeline.connection_key: {
        'edges': [{'node': node} for node in nodes], 'page_info': {'has_next_page': more},
    }}}


def test_supplied_example_ignores_other_feed_and_discovery_order():
    timeline = ProfileTimeline()
    # Supplied shortcodes; synthetic timestamps describe the required ordering.
    timeline.consume(payload([{'code': 'BCP_gsMu-WY', 'taken_at': 1}], True))
    timeline.consume({'data': {'xdt_api__v1__feed__timeline__connection': {
        'edges': [{'node': {'code': 'ChHWVFcIaCz', 'taken_at': 2}}],
        'page_info': {'has_next_page': False},
    }}})
    assert not timeline.complete
    timeline.consume(payload([{'code': 'ChHWVFcIaCz', 'taken_at': 2, 'product_type': 'clips'}], False))
    assert timeline.complete
    assert _select_unseen_media_paths(timeline.paths(), set(), 1) == ['/p/BCP_gsMu-WY/']
    assert _select_unseen_media_paths(timeline.paths(), {'BCP_gsMu-WY'}, 1) == ['/reel/ChHWVFcIaCz/']


def test_profile_completion_stops_without_scanning_other_feeds():
    timeline = ProfileTimeline()
    class Page:
        def evaluate(self, script): pass
        def wait_for_timeout(self, milliseconds):
            timeline.consume(payload([{'code': 'oldest', 'taken_at': 1}], False))
    assert _scroll_profile_until_complete(Page(), 'example', timeline) == ['/p/oldest/']


def test_stalled_partial_profile_never_selects_a_post():
    timeline = ProfileTimeline()
    timeline.consume(payload([{'code': 'newer', 'taken_at': 2}], True))
    class Page:
        def evaluate(self, script): pass
        def wait_for_timeout(self, milliseconds): pass
    with pytest.raises(IncompleteProfileError, match='did not confirm'):
        _scroll_profile_until_complete(Page(), 'example', timeline)


def test_missing_publication_time_skips_only_that_node():
    timeline = ProfileTimeline()
    timeline.consume(payload([{'code': 'unknown'}, {'code': 'good', 'taken_at': 1}], False))
    assert not timeline.invalid
    assert timeline.complete
    assert timeline.paths() == ['/p/good/']
    assert timeline.skipped_edges == 1


def test_partial_graphql_error_cannot_confirm_completion():
    timeline = ProfileTimeline()
    result = payload([{'code': 'candidate', 'taken_at': 1}], False)
    result['errors'] = [{'message': 'Partial response'}]
    timeline.consume(result)
    assert timeline.invalid and not timeline.complete


def test_single_malformed_edge_does_not_abort_profile_scan():
    """A null node on page 1 must not abort the scan; the valid posts are returned."""
    timeline = ProfileTimeline()
    pages = iter([
        {
            "data": {
                ProfileTimeline.connection_key: {
                    "edges": [{"node": None}, {"node": {"code": "newer", "taken_at": 2}}],
                    "page_info": {"has_next_page": True},
                }
            }
        },
        payload([{"code": "bad!code", "taken_at": 3}, {"code": "oldest", "taken_at": 1}], False),
    ])

    class FakePage:
        def evaluate(self, script):
            pass
        def wait_for_timeout(self, milliseconds):
            page = next(pages, None)
            if page is not None:
                timeline.consume(page)

    result = _scroll_profile_until_complete(FakePage(), "example", timeline)
    assert result == ["/p/newer/", "/p/oldest/"]
    assert timeline.skipped_edges == 2
    assert _select_unseen_media_paths(result, set(), 1) == ["/p/oldest/"]


@pytest.mark.parametrize("bad_page", [
    # page_info missing
    {"data": {ProfileTimeline.connection_key: {"edges": [], "page_info": None}}},
    # edges not a list
    {"data": {ProfileTimeline.connection_key: {"edges": "nope", "page_info": {"has_next_page": False}}}},
    # has_next_page missing
    {"data": {ProfileTimeline.connection_key: {"edges": [], "page_info": {}}}},
    # has_next_page is a string, not bool
    {"data": {ProfileTimeline.connection_key: {"edges": [], "page_info": {"has_next_page": "false"}}}},
])
def test_structural_page_errors_still_invalidate(bad_page):
    timeline = ProfileTimeline()
    timeline.consume(bad_page)
    assert timeline.invalid
    assert not timeline.complete


def test_structural_error_still_raises_incomplete_error():
    timeline = ProfileTimeline()
    bad_page = {"data": {ProfileTimeline.connection_key: {"edges": [], "page_info": None}}}

    class FakePage:
        def evaluate(self, script):
            pass
        def wait_for_timeout(self, milliseconds):
            timeline.consume(bad_page)

    with pytest.raises(IncompleteProfileError):
        _scroll_profile_until_complete(FakePage(), "example", timeline)
