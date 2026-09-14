"""Exercise shopping-list persistence in a real browser with an isolated API."""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import sync_playwright

from cookbook.report_html import render_shopping_list_html


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as error:
            pytest.skip(f"Chromium unavailable: {type(error).__name__}")
        page = browser.new_page()
        yield page
        browser.close()


def test_queued_saves_preserve_legacy_and_reject_conflicts(page):
    legacy = [{"id": "old", "name": "Legacy", "done": False}]
    page.add_init_script(f'localStorage.setItem("cookbook-shopping-list", {json.dumps(json.dumps(legacy))})')
    writes = []
    def api(route):
        if route.request.method == "GET":
            route.fulfill(json={"items": [], "revision": 5})
        else:
            payload = route.request.post_data_json
            writes.append(payload)
            route.fulfill(status=409 if len(writes) == 3 else 200,
                          json={"revision": payload["revision"] + 1})
    page.route("http://cookbook.test/api/shopping-list", api)
    page.route("http://cookbook.test/shopping_list.html", lambda route: route.fulfill(
        content_type="text/html", body=render_shopping_list_html("favicon.svg")))
    page.goto("http://cookbook.test/shopping_list.html")
    page.wait_for_function("!document.getElementById('shopping-item-input').disabled")
    page.evaluate("""() => {
        for (const name of ['Milk', 'Eggs', 'Bread']) {
            document.getElementById('shopping-item-input').value = name;
            document.getElementById('shopping-form').requestSubmit();
        }
    }""")
    page.wait_for_function("document.getElementById('export-status').textContent.includes('another tab')")
    assert [write["revision"] for write in writes] == [5, 6, 7]
    assert [len(write["items"]) for write in writes] == [1, 2, 3]
    assert "another tab" in page.locator("#export-status").inner_text()
    assert json.loads(page.evaluate('localStorage.getItem("cookbook-shopping-list")')) == legacy
    backups = page.evaluate('Object.keys(localStorage).filter(key => key.startsWith("cookbook-shopping-list-backup-"))')
    assert len(backups) == 1
    assert len(json.loads(page.evaluate("key => localStorage.getItem(key)", backups[0]))) == 3
    page.locator("#shopping-item-input").fill("Salt")
    page.locator("#shopping-form").evaluate("form => form.requestSubmit()")
    page.wait_for_function("document.getElementById('export-status').textContent.includes('Reload before')")
    assert len(writes) == 3


def test_failed_load_disables_editing_and_retains_browser_copy(page):
    page.add_init_script('localStorage.setItem("cookbook-shopping-list", "[]")')
    page.route("http://cookbook.test/api/shopping-list", lambda route: route.fulfill(status=503, json={}))
    page.route("http://cookbook.test/shopping_list.html", lambda route: route.fulfill(
        content_type="text/html", body=render_shopping_list_html("favicon.svg")))
    page.goto("http://cookbook.test/shopping_list.html")
    page.wait_for_function("document.getElementById('shopping-item-input').disabled")
    assert "Unable to load" in page.locator("#export-status").inner_text()
    assert page.evaluate('localStorage.getItem("cookbook-shopping-list")') == "[]"
