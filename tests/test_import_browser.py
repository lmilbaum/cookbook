"""Verify the import button uses the application API and never imports on load."""
from __future__ import annotations

from cookbook.report_html import render_html
from test_shopping_browser import page


def test_import_button_starts_once_and_shows_completion(page):
    calls = []
    state = {'status': 'idle', 'message': ''}
    def api(route):
        calls.append(route.request.method)
        if route.request.method == 'POST':
            assert route.request.post_data_json == {}
            state.update(status='running', message='Importing…')
        route.fulfill(json=state)
    page.route('http://cookbook.test/api/import-post', api)
    page.route('http://cookbook.test/api/recipe-state', lambda route: route.fulfill(
        json={'revision': 1, 'state': {'overrides': {}, 'custom': []}}))
    page.route('http://cookbook.test/lizapanelim_posts.html', lambda route: route.fulfill(
        content_type='text/html', body=render_html([], 'example', 'favicon.svg')))
    page.goto('http://cookbook.test/lizapanelim_posts.html')
    button = page.get_by_role('button', name='Import next post from the end')
    page.wait_for_function("!document.getElementById('import-post').disabled")
    assert calls == ['GET']
    button.click()
    page.wait_for_function("document.getElementById('import-status').textContent === 'Importing…'")
    assert button.is_disabled()
    state.update(status='succeeded', message='Post imported.')
    page.locator('#import-refresh').wait_for(state='visible')
    assert not button.is_disabled()
    assert calls.count('POST') == 1
    assert page.url == 'http://cookbook.test/lizapanelim_posts.html'


def test_import_button_hidden_for_static_file(page, tmp_path):
    report = tmp_path / 'cookbook.html'
    report.write_text(render_html([], 'example', 'favicon.svg'))
    page.goto(report.as_uri())
    assert page.locator('#import-controls').is_hidden()
