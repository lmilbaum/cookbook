"""Exercise the made-recipes filter in a real browser."""
from __future__ import annotations

import io
from datetime import datetime

import pytest
from playwright.sync_api import expect
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cookbook import server
from cookbook.database import Base, session_scope
from cookbook.made_date_repository import list_made_dates

from cookbook.models import Post, Recipe
from cookbook.site_pages import render_html

BASE = "http://cookbook.test"


def _recipe(recipe_id: str, title: str) -> Recipe:
    recipe = Recipe(
        id=recipe_id, image_url="", caption=title, timestamp_utc="2026-08-24T12:00:00Z",
        title=title, recipe_url="", recipe_name="", source="lizapanelim",
    )
    recipe.post = Post(shortcode=recipe_id, url=f"https://www.instagram.com/p/{recipe_id}/", typename="GraphImage", is_video=False)
    return recipe


def _setup_page(page, recipes, made_recipe_ids=None, made_recipes_status=None):
    """Setup common routes and return a state object for tracking API calls."""
    made_recipe_ids = made_recipe_ids or []
    made_recipes_status = made_recipes_status or 200

    state = {"made_dates_gets": {}, "made_dates_posts": []}

    def made_recipes_route(route):
        if made_recipes_status == 503:
            route.fulfill(status=503, json={"error": "Unable to read made recipes"})
        else:
            route.fulfill(json={"recipe_ids": made_recipe_ids})

    def made_dates_route(route):
        recipe_id = route.request.url.split("/")[-2]
        if route.request.method == "GET":
            state["made_dates_gets"].setdefault(recipe_id, [])
            route.fulfill(json={"dates": state["made_dates_gets"][recipe_id]})
        elif route.request.method == "POST":
            state["made_dates_posts"].append(route.request.post_data_json)
            date_str = route.request.post_data_json["date"]
            state["made_dates_gets"].setdefault(recipe_id, []).insert(0, date_str)
            made_recipe_ids.append(recipe_id)
            route.fulfill(json={"dates": state["made_dates_gets"][recipe_id]})
        elif route.request.method == "DELETE":
            date_str = route.request.url.split("/")[-1]
            if date_str in state["made_dates_gets"].get(recipe_id, []):
                state["made_dates_gets"][recipe_id].remove(date_str)
                if recipe_id in made_recipe_ids:
                    made_recipe_ids.remove(recipe_id)
            route.fulfill(json={"dates": state["made_dates_gets"].get(recipe_id, [])})

    page.route(f"{BASE}/api/made-recipes", made_recipes_route)
    page.route(f"{BASE}/api/recipes/*/made-dates*", made_dates_route)
    page.route(f"{BASE}/api/recipe-state", lambda route: route.fulfill(json={"revision": 1, "state": {"overrides": {}, "custom": []}}))
    page.route(f"{BASE}/api/import-post", lambda route: route.fulfill(json={"status": "idle", "message": ""}))
    page.route(f"{BASE}/api/recipe-types", lambda route: route.fulfill(json=[]))
    page.route(f"{BASE}/index.html*", lambda route: route.fulfill(
        content_type="text/html", body=render_html(recipes, "favicon.svg")))
    page.goto(f"{BASE}/index.html")
    page.locator("#recipe-grid").wait_for()
    return state


def test_made_filter_shows_only_recipes_marked_as_made(page):
    """Recipes marked as made appear when 'made' filter is selected."""
    r1, r2 = _recipe("r1", "Salad"), _recipe("r2", "Soup")
    _setup_page(page, [r1, r2], made_recipe_ids=["r2"])

    # Both cards visible initially
    assert page.locator(".card").count() == 2

    # Wait for made filter to be enabled
    made_select = page.locator("#search-made")
    expect(made_select).to_be_enabled()

    # Select "made"
    made_select.select_option("made")
    page.wait_for_function("document.querySelectorAll('.card:not([hidden])').length === 1")
    assert page.locator(".card:not([hidden])").count() == 1
    assert page.locator(".card:not([hidden]) .card-title").inner_text() == "Soup"

    # Select "all"
    made_select.select_option("all")
    page.wait_for_function("document.querySelectorAll('.card:not([hidden])').length === 2")
    assert page.locator(".card:not([hidden])").count() == 2


def test_made_filter_shows_recipes_not_yet_made(page):
    """Recipes not yet made appear when 'not_made' filter is selected."""
    r1, r2 = _recipe("r1", "Salad"), _recipe("r2", "Soup")
    _setup_page(page, [r1, r2], made_recipe_ids=["r2"])

    made_select = page.locator("#search-made")
    made_select.wait_for()

    # Select "not_made"
    made_select.select_option("not_made")
    page.wait_for_function("document.querySelectorAll('.card:not([hidden])').length === 1")
    assert page.locator(".card:not([hidden])").count() == 1
    assert page.locator(".card:not([hidden]) .card-title").inner_text() == "Salad"


def test_made_filter_with_nothing_made_shows_no_results_message(page):
    """No results message shows when filtering for made recipes but none exist."""
    r1, r2 = _recipe("r1", "Salad"), _recipe("r2", "Soup")
    _setup_page(page, [r1, r2], made_recipe_ids=[])

    made_select = page.locator("#search-made")
    made_select.wait_for()

    # Select "made" when no recipes are made
    made_select.select_option("made")
    page.wait_for_function("!document.getElementById('no-filter-results').hidden")
    assert page.locator("#no-filter-results").is_hidden() == False


def test_marking_a_recipe_made_in_the_popup_updates_the_filter(page):
    """Marking a recipe as made updates the made filter live."""
    r1, r2 = _recipe("r1", "Salad"), _recipe("r2", "Soup")
    page = page.context.browser.new_page(timezone_id="UTC")
    page.clock.set_fixed_time(datetime.fromisoformat("2026-09-15T12:00:00+00:00"))
    state = _setup_page(page, [r1, r2], made_recipe_ids=[])

    made_select = page.locator("#search-made")
    made_select.wait_for()

    # Open popup for r1 and mark as made
    page.locator(".card-title a", has_text="Salad").click()
    page.locator("#recipe-page").wait_for()
    expect(page.locator("#recipe-page input[type=date]")).to_have_count(0)
    page.locator("#recipe-page .mark-made").click()

    # Wait for the mark to be processed (date appears in the list)
    expect(page.locator("#recipe-page .made-dates-list li time")).to_have_attribute(
        "datetime", "2026-09-15"
    )
    assert state["made_dates_posts"] == [{"date": "2026-09-15"}]

    # Close the popup
    page.locator("#close-recipe-page").click()
    page.wait_for_function("!document.getElementById('recipe-page').open")

    # Now select "made" filter - only r1 should be visible
    made_select.select_option("made")
    page.wait_for_function("document.querySelectorAll('.card:not([hidden])').length === 1")

    # Verify r1 is visible
    assert page.locator(".card:not([hidden]) .card-title").inner_text() == "Salad"


def test_made_filter_stays_disabled_when_made_recipes_cannot_load(page):
    """Made filter remains disabled if the made-recipes endpoint fails."""
    r1, r2 = _recipe("r1", "Salad"), _recipe("r2", "Soup")
    _setup_page(page, [r1, r2], made_recipe_ids=[], made_recipes_status=503)

    made_select = page.locator("#search-made")
    # Made select stays disabled on error
    expect(made_select).to_have_attribute("disabled", "")
    # Both cards still visible
    assert page.locator(".card").count() == 2


@pytest.mark.parametrize(
    ("timezone_id", "opened_at", "clicked_at", "expected_date"),
    [
        ("Asia/Jerusalem", "2026-09-15T21:30:00+00:00", None, "2026-09-16"),
        ("America/Los_Angeles", "2026-09-15T00:30:00+00:00", None, "2026-09-14"),
        ("Asia/Jerusalem", "2026-09-15T20:59:00+00:00",
         "2026-09-15T21:01:00+00:00", "2026-09-16"),
    ],
)
def test_mark_as_made_saves_local_click_date(
    page, tmp_path, timezone_id, opened_at, clicked_at, expected_date
):
    """The actual browser POST stores the local day at click time, once per day."""
    page = page.context.browser.new_page(timezone_id=timezone_id)
    page.clock.set_fixed_time(datetime.fromisoformat(opened_at))
    recipe = _recipe("r1", "Salad")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_scope(factory) as session:
        session.add(recipe)
    state = _setup_page(page, [recipe])
    responses = []
    bodies = []

    def save_made_date(route):
        if route.request.method != "POST":
            route.fallback()
            return
        body = route.request.post_data.encode()
        bodies.append(route.request.post_data_json)
        handler = object.__new__(server.make_handler(tmp_path, factory))
        handler.path = "/api/recipes/r1/made-dates"
        handler.headers = {
            "Content-Type": "application/json", "Content-Length": str(len(body))
        }
        handler.rfile = io.BytesIO(body)
        handler._json_response = lambda status, payload: responses.append((status, payload))
        handler.do_POST()
        status, payload = responses[-1]
        state["made_dates_gets"]["r1"] = payload["dates"]
        route.fulfill(status=status, json=payload)

    page.route(f"{BASE}/api/recipes/r1/made-dates", save_made_date)
    page.locator(".card-title a", has_text="Salad").click()
    expect(page.locator("#recipe-page input[type=date]")).to_have_count(0)
    if clicked_at:
        page.clock.set_fixed_time(datetime.fromisoformat(clicked_at))
    button = page.locator("#recipe-page .mark-made")
    expect(page.locator("#recipe-page .recipe-made-dates h3")).to_have_count(0)
    expect(button).to_have_text("הכנתי היום")
    expect(button).to_have_attribute("aria-label", "הכנתי היום")
    assert button.get_attribute("title") is None
    button.click()
    history = page.locator("#recipe-page .made-dates-list li time")
    expect(history).to_have_attribute("datetime", expected_date)
    assert bodies == [{"date": expected_date}]
    assert responses == [(201, {"dates": [expected_date]})]
    assert list_made_dates(factory, "r1") == [expected_date]

    expect(button).to_be_enabled()
    button.click()
    expect(button).to_be_enabled()
    assert len(bodies) == 2
    expect(history).to_have_count(1)
    assert list_made_dates(factory, "r1") == [expected_date]
    engine.dispose()
