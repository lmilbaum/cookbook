"""Verify the import button uses the application API and never imports on load."""
from __future__ import annotations

from cookbook.site_pages import render_html


def test_import_button_starts_once_and_shows_completion(page):
    calls = []
    state = {'status': 'idle', 'code': '', 'message': '', 'reason_code': ''}
    def api(route):
        calls.append(route.request.method)
        if route.request.method == 'POST':
            assert route.request.post_data_json == {}
            state.update(status='running', code='running', message='English fallback')
        route.fulfill(json=state)
    page.route('http://cookbook.test/api/import-post', api)
    page.route('http://cookbook.test/api/recipe-state', lambda route: route.fulfill(
        json={'revision': 1, 'state': {'overrides': {}, 'custom': []}}))
    page.route('http://cookbook.test/index.html', lambda route: route.fulfill(
        content_type='text/html', body=render_html([], 'favicon.svg', locale='en')))
    page.goto('http://cookbook.test/index.html')
    button = page.get_by_role('button', name='Import next post from the end')
    page.wait_for_function("!document.getElementById('import-post').disabled")
    assert calls == ['GET']
    button.click()
    page.wait_for_function("document.getElementById('import-status').textContent.startsWith('Finding the oldest post')")
    assert button.is_disabled()
    state.update(status='succeeded', code='succeeded', message='English fallback')
    page.locator('#import-refresh').wait_for(state='visible')
    assert not button.is_disabled()
    assert calls.count('POST') == 1
    assert page.url == 'http://cookbook.test/index.html'


def test_import_button_hidden_for_static_file(page, tmp_path):
    report = tmp_path / 'cookbook.html'
    report.write_text(render_html([], 'favicon.svg', locale='en'))
    page.goto(report.as_uri())
    assert page.locator('#import-controls').is_hidden()


def _status_text(page, locale, state):
    """Render the cookbook in a locale, feed it a server status, and return the shown text."""
    page.route('http://cookbook.test/api/import-post', lambda route: route.fulfill(json=state))
    page.route('http://cookbook.test/api/recipe-state', lambda route: route.fulfill(
        json={'revision': 1, 'state': {'overrides': {}, 'custom': []}}))
    page.route('http://cookbook.test/index.html', lambda route: route.fulfill(
        content_type='text/html', body=render_html([], 'favicon.svg', locale=locale)))
    page.goto('http://cookbook.test/index.html')
    page.wait_for_function("document.getElementById('import-status').textContent !== ''")
    return page.locator('#import-status').text_content()


def test_import_messages_follow_the_page_language_not_the_servers_english(page):
    """Regression: the server's English message was shown verbatim on the Hebrew page."""
    state = {'status': 'succeeded', 'code': 'succeeded', 'reason_code': '',
             'message': 'Post imported. Refresh the cookbook to view it.'}
    text = _status_text(page, 'he', state)
    assert text == 'הפוסט יובא. רעננו את ספר המתכונים כדי לראות אותו.'


def test_incomplete_scan_shows_the_translated_reason(page):
    state = {'status': 'failed', 'code': 'incomplete', 'reason_code': 'pagination_unconfirmed',
             'message': 'Could not finish scanning for the oldest post. Reason: Instagram did not confirm'}
    text = _status_text(page, 'he', state)
    assert 'סיבה: אינסטגרם לא אישרה את סוף העימוד של הפרופיל; לא נבחר פוסט.' in text
    assert 'Instagram' not in text


def test_unknown_status_code_falls_back_to_the_servers_message(page):
    state = {'status': 'failed', 'code': 'from-a-newer-server', 'message': 'Something specific', 'reason_code': ''}
    assert _status_text(page, 'he', state) == 'Something specific'
