"""Fixtures shared by the browser tests."""
from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as error:
            pytest.skip(f"Chromium unavailable: {type(error).__name__}")
        page = browser.new_page()
        yield page
        browser.close()
