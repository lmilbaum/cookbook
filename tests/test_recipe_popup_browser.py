"""Open a recipe as a popup over the home page and return home on save."""
from __future__ import annotations

from cookbook.models import Post, Recipe
from cookbook.recipe_state_repository import valid_state
from cookbook.site_pages import render_html

BASE = "http://cookbook.test"


def _recipe(recipe_id: str, title: str) -> Recipe:
    recipe = Recipe(
        id=recipe_id, image_url="", caption=title, timestamp_utc="2026-08-24T12:00:00Z",
        title=title, recipe_url="", recipe_name="", source="lizapanelim",
    )
    recipe.post = Post(
        shortcode=recipe_id, url=f"https://www.instagram.com/p/{recipe_id}/", typename="GraphImage", is_video=False,
    )
    return recipe


def _serve(page) -> dict:
    store = {"state": {"overrides": {}, "custom": []}, "revision": 1, "puts": []}

    def recipe_state(route):
        if route.request.method == "PUT":
            body = route.request.post_data_json
            if body["revision"] != store["revision"] or not valid_state(body["state"]):
                route.fulfill(status=409 if valid_state(body["state"]) else 400, json={"error": "rejected"})
                return
            store["state"], store["revision"] = body["state"], store["revision"] + 1
            store["puts"].append(body["state"])
            route.fulfill(json={"revision": store["revision"]})
        else:
            route.fulfill(json={"revision": store["revision"], "state": store["state"]})

    page.route(f"{BASE}/api/recipe-state", recipe_state)
    page.route(f"{BASE}/api/recipe-types", lambda route: route.fulfill(status=201, json={"id": 1, "name": "x"})
               if route.request.method == "POST" else route.fulfill(json=[]))
    page.route(f"{BASE}/api/import-post", lambda route: route.fulfill(json={"status": "idle", "message": ""}))
    page.route(f"{BASE}/index.html*", lambda route: route.fulfill(
        content_type="text/html",
        body=render_html([_recipe("r1", "Salad"), _recipe("r2", "Soup")], "favicon.svg")))
    return store


def test_clicking_a_recipe_opens_a_popup_over_the_home_page(page) -> None:
    _serve(page)
    page.goto(f"{BASE}/index.html")
    page.locator("#recipe-grid .recipe-detail-link", has_text="Soup").click()

    popup = page.locator("#recipe-page")
    popup.wait_for()
    assert popup.evaluate("dialog => dialog.open")
    assert page.url == f"{BASE}/index.html?recipe=r2"
    assert page.locator("#recipe-title").input_value() == "Soup"
    assert popup.locator(".recipe-ingredients").is_visible()
    assert page.locator("#recipe-grid [data-recipe-id]:visible").count() == 2  # home page stays behind


def test_saving_closes_the_popup_and_returns_to_the_home_page(page) -> None:
    store = _serve(page)
    page.goto(f"{BASE}/index.html")
    page.locator("#recipe-grid .recipe-detail-link", has_text="Salad").click()
    page.locator("#recipe-title").fill("Green salad")
    page.locator("#recipe-form button[type=submit]").click()

    page.wait_for_function("!document.getElementById('recipe-page').open")
    page.wait_for_url(f"{BASE}/index.html")
    assert store["puts"][-1]["overrides"]["r1"]["title"] == "Green salad"
    assert page.locator("#recipe-grid .recipe-detail-link").all_inner_texts() == ["Green salad", "Soup"]
    # The form went back to the add-recipe dialog, so adding still works.
    page.locator("#add-recipe").click()
    assert page.locator("#recipe-dialog #recipe-form").is_visible()


def test_a_recipe_link_opens_the_popup_and_closing_it_shows_the_home_page(page) -> None:
    _serve(page)
    page.goto(f"{BASE}/index.html?recipe=r1")
    page.wait_for_function("document.getElementById('recipe-page').open")
    assert page.locator("#recipe-title").input_value() == "Salad"

    page.locator("#close-recipe-page").click()
    page.wait_for_function("!document.getElementById('recipe-page').open")
    page.wait_for_url(f"{BASE}/index.html")
    assert page.locator("#recipe-grid [data-recipe-id]:visible").count() == 2


def test_back_button_closes_the_popup(page) -> None:
    _serve(page)
    page.goto(f"{BASE}/index.html")
    page.locator("#recipe-grid .recipe-detail-link", has_text="Soup").click()
    page.wait_for_function("document.getElementById('recipe-page').open")

    page.go_back()
    page.wait_for_function("!document.getElementById('recipe-page').open")
    page.wait_for_url(f"{BASE}/index.html")


def test_notes_typed_in_the_popup_keep_the_type_chosen_there(page) -> None:
    """The popup card is a copy; edits must build on the grid card's latest recipe."""
    store = _serve(page)
    page.goto(f"{BASE}/index.html")
    page.locator("#recipe-grid .recipe-detail-link", has_text="Salad").click()
    page.locator("#recipe-type").fill("Soups")
    page.locator("#recipe-type").press("Enter")
    page.wait_for_function("document.getElementById('save-status').textContent !== ''")
    page.locator("#recipe-page .recipe-notes textarea").fill("Less salt")
    page.wait_for_function("document.querySelector('#recipe-page .recipe-notes-status').textContent !== ''")
    page.wait_for_timeout(100)

    saved = store["puts"][-1]["overrides"]["r1"]
    assert saved["type"] == "Soups"
    assert saved["notes"] == "Less salt"
