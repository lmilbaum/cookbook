"""Verify the import button uses the application API and never imports on load."""
from __future__ import annotations

import pytest

from cookbook.site_pages import render_html


def test_import_button_starts_once_and_refreshes_without_completion_notice(page):
    calls = []
    documents = []
    state = {'status': 'idle', 'code': '', 'message': '', 'reason_code': ''}
    def api(route):
        calls.append(route.request.method)
        if route.request.method == 'POST':
            assert route.request.post_data_json == {}
            state.update(status='running', code='running', message='English fallback', reviewed_posts=12)
        route.fulfill(json=state)
    page.route('http://cookbook.test/api/import-post', api)
    page.route('http://cookbook.test/api/recipe-state', lambda route: route.fulfill(
        json={'revision': 1, 'state': {'overrides': {}, 'custom': []}}))
    def document(route):
        documents.append(route.request.url)
        route.fulfill(content_type='text/html', body=render_html([], 'favicon.svg', locale='en'))
    page.route('http://cookbook.test/index.html', document)
    page.goto('http://cookbook.test/index.html')
    button = page.get_by_role('button', name='Import next post from the end')
    page.wait_for_function("!document.getElementById('import-post').disabled")
    assert calls == ['GET']
    button.click()
    page.wait_for_function("document.getElementById('import-count').textContent === 'Posts reviewed: 12'")
    assert page.locator('#import-progress').is_visible()
    assert page.locator('#import-status').text_content() == ''
    state['reviewed_posts'] = 24
    page.wait_for_function("document.getElementById('import-count').textContent === 'Posts reviewed: 24'")
    assert button.is_disabled()
    state.update(status='succeeded', code='succeeded', message='English fallback')
    page.wait_for_function("!document.getElementById('import-post').disabled && document.getElementById('import-progress').hidden")
    assert page.locator('#import-status').text_content() == ''
    # Wait for the page to reload after the import succeeds (1000ms timeout + some margin)
    page.wait_for_timeout(1200)
    button = page.get_by_role('button', name='Import next post from the end')
    assert not button.is_disabled()
    assert calls.count('POST') == 1
    assert page.url == 'http://cookbook.test/index.html'
    assert len(documents) == 2
    page.wait_for_timeout(1500)
    assert len(documents) == 2


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
    page.wait_for_function("!document.getElementById('import-post').disabled && document.getElementById('import-progress').hidden")
    return page.locator('#import-status').text_content()


@pytest.mark.parametrize('locale', ['he', 'en'])
def test_success_has_no_completion_notice_or_server_fallback(page, locale):
    """Success stays silent even when the server sends a completion message."""
    state = {'status': 'succeeded', 'code': 'succeeded', 'reason_code': '',
             'message': 'Post imported. Refresh the cookbook to view it.'}
    text = _status_text(page, locale, state)
    assert text == ''
    page.wait_for_timeout(1500)
    assert page.locator('#import-status').text_content() == ''


def test_incomplete_scan_shows_the_translated_reason(page):
    state = {'status': 'failed', 'code': 'incomplete', 'reason_code': 'pagination_unconfirmed',
             'message': 'Could not finish scanning for the oldest post. Reason: Instagram did not confirm'}
    text = _status_text(page, 'he', state)
    assert 'סיבה: אינסטגרם לא אישרה את סוף העימוד של הפרופיל; לא נבחר פוסט.' in text
    assert 'Instagram' not in text


def test_unknown_status_code_falls_back_to_the_servers_message(page):
    state = {'status': 'failed', 'code': 'from-a-newer-server', 'message': 'Something specific', 'reason_code': ''}
    assert _status_text(page, 'he', state) == 'Something specific'


def test_attached_running_import_has_hebrew_accessibility_and_failure_does_not_reload(page):
    state = {'status': 'running', 'code': 'running', 'reviewed_posts': 12, 'message': ''}
    documents = []
    page.route('http://cookbook.test/api/import-post', lambda route: route.fulfill(json=state))
    page.route('http://cookbook.test/api/recipe-state', lambda route: route.fulfill(
        json={'revision': 1, 'state': {'overrides': {}, 'custom': []}}))
    def document(route):
        documents.append(route.request.url)
        route.fulfill(content_type='text/html', body=render_html([], 'favicon.svg', locale='he'))
    page.route('http://cookbook.test/index.html', document)
    page.goto('http://cookbook.test/index.html')
    page.wait_for_function("document.getElementById('import-count').textContent === 'פוסטים שנבדקו: 12'")
    assert page.get_by_role('status', name='התקדמות הייבוא').is_visible()
    assert page.locator('#import-progress svg').get_attribute('aria-hidden') == 'true'
    state.update(status='failed', code='failed')
    page.wait_for_function("document.getElementById('import-status').textContent !== ''")
    assert page.locator('#import-progress').is_hidden()
    page.wait_for_timeout(1500)
    assert len(documents) == 1


def test_rejected_import_does_not_reload_for_prior_success(page):
    """A failed new POST must not turn a previous job's success into a refresh."""
    state = {'status': 'succeeded', 'code': 'succeeded', 'reviewed_posts': 24, 'message': ''}
    documents = []
    posts = []
    def api(route):
        if route.request.method == 'POST':
            posts.append(True)
            route.fulfill(status=500, json={})
        else:
            route.fulfill(json=state)
    page.route('http://cookbook.test/api/import-post', api)
    page.route('http://cookbook.test/api/recipe-state', lambda route: route.fulfill(
        json={'revision': 1, 'state': {'overrides': {}, 'custom': []}}))
    def document(route):
        documents.append(route.request.url)
        route.fulfill(content_type='text/html', body=render_html([], 'favicon.svg', locale='en'))
    page.route('http://cookbook.test/index.html', document)
    page.goto('http://cookbook.test/index.html')
    page.wait_for_function("!document.getElementById('import-post').disabled")
    page.get_by_role('button', name='Import next post from the end').click()
    page.wait_for_function("!document.getElementById('import-post').disabled")
    page.wait_for_timeout(1500)
    assert posts == [True]
    assert documents == ['http://cookbook.test/index.html']
    assert page.locator('#import-progress').is_hidden()


def _recipe(recipe_id, title):
    from cookbook.models import Post, Recipe
    recipe = Recipe(id=recipe_id, title=title, caption=title, image_url='', timestamp_utc='2026-01-01')
    recipe.post = Post(shortcode=recipe_id, url=f'https://www.instagram.com/p/{recipe_id}/', typename='GraphImage', is_video=False)
    return recipe


@pytest.mark.parametrize('selected', [False, True])
def test_success_opens_exact_imported_recipe_after_refresh_once(page, selected):
    calls, documents = [], []
    state = {'status': 'idle', 'code': '', 'message': ''}
    old = _recipe('older', 'Older recipe')
    imported = _recipe('actual_Post-1', 'Imported recipe')
    def api(route):
        calls.append(route.request.method)
        if route.request.method == 'POST':
            state.update(status='running', code='running', reviewed_posts=12)
        route.fulfill(json=state)
    page.route('http://cookbook.test/api/import-post', api)
    page.route('http://cookbook.test/api/recipe-state', lambda route: route.fulfill(
        json={'revision': 1, 'state': {'overrides': {}, 'custom': []}}))
    page.route('http://cookbook.test/api/recipes/*/made-dates', lambda route: route.fulfill(json=[]))
    def document(route):
        documents.append(route.request.url)
        recipes = [old] if len(documents) == 1 else [old, imported]
        route.fulfill(content_type='text/html', body=render_html(recipes, 'favicon.svg', locale='en'))
    page.route('http://cookbook.test/index.html*', document)
    page.goto('http://cookbook.test/index.html' + ('?recipe=older' if selected else ''))
    page.wait_for_function("!document.getElementById('import-post').disabled")
    if selected:
        # Keep the older URL selection while starting the import behind its dialog.
        page.evaluate("document.getElementById('import-post').click()")
    else:
        page.get_by_role('button', name='Import next post from the end').click()
    page.wait_for_function("document.getElementById('import-count').textContent === 'Posts reviewed: 12'")
    state.update(status='succeeded', code='succeeded', imported_recipe_id='actual_Post-1', message='Ignored completion')
    page.wait_for_function("document.getElementById('recipe-page').open && document.getElementById('recipe-title').value === 'Imported recipe'")
    assert len(documents) == 2
    assert calls.count('POST') == 1
    assert page.url.endswith('?recipe=actual_Post-1')
    assert page.locator('#import-status').text_content() == ''
    assert page.evaluate("sessionStorage.getItem('cookbook-imported-recipe')") is None
    page.locator('#close-recipe-page').click()
    page.wait_for_function("!location.search && !document.getElementById('recipe-page').open")
    page.reload()
    page.wait_for_function("!document.getElementById('import-post').disabled")
    assert not page.locator('#recipe-page').evaluate('dialog => dialog.open')
    page.wait_for_timeout(1200)
    assert len(documents) == 3


@pytest.mark.parametrize('status,recipe_id', [('succeeded', 'actual_Post-1'), ('failed', 'actual_Post-1'), ('empty', '')])
def test_initial_terminal_status_does_not_open_recipe(page, status, recipe_id):
    state = {'status': status, 'code': status, 'message': '', 'imported_recipe_id': recipe_id}
    page.route('http://cookbook.test/api/import-post', lambda route: route.fulfill(json=state))
    page.route('http://cookbook.test/api/recipe-state', lambda route: route.fulfill(
        json={'revision': 1, 'state': {'overrides': {}, 'custom': []}}))
    page.route('http://cookbook.test/index.html', lambda route: route.fulfill(
        content_type='text/html', body=render_html([_recipe('actual_Post-1', 'Imported recipe')], 'favicon.svg', locale='en')))
    page.goto('http://cookbook.test/index.html')
    page.wait_for_function("!document.getElementById('import-post').disabled")
    page.wait_for_timeout(1200)
    assert not page.locator('#recipe-page').evaluate('dialog => dialog.open')
    assert page.evaluate("sessionStorage.getItem('cookbook-imported-recipe')") is None


@pytest.mark.parametrize('recipe_id,blocked_storage', [('', False), ('unknown', False), ('actual_Post-1', True)])
def test_success_without_available_handoff_still_refreshes_safely(page, recipe_id, blocked_storage):
    state = {'status': 'running', 'code': 'running', 'message': ''}
    documents = []
    if blocked_storage:
        page.add_init_script("Storage.prototype.setItem = () => { throw new Error('Unavailable'); }")
    page.route('http://cookbook.test/api/import-post', lambda route: route.fulfill(json=state))
    page.route('http://cookbook.test/api/recipe-state', lambda route: route.fulfill(
        json={'revision': 1, 'state': {'overrides': {}, 'custom': []}}))
    def document(route):
        documents.append(route.request.url)
        route.fulfill(content_type='text/html', body=render_html([_recipe('actual_Post-1', 'Imported recipe')], 'favicon.svg', locale='en'))
    page.route('http://cookbook.test/index.html', document)
    page.goto('http://cookbook.test/index.html')
    page.wait_for_function("document.getElementById('import-post').disabled")
    state.update(status='succeeded', code='succeeded', imported_recipe_id=recipe_id)
    page.wait_for_function("!document.getElementById('import-post').disabled")
    page.wait_for_timeout(1300)
    assert len(documents) == 2
    assert not page.locator('#recipe-page').evaluate('dialog => dialog.open')
    assert page.evaluate("sessionStorage.getItem('cookbook-imported-recipe')") is None
