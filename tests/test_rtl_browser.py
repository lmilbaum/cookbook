"""Check right-to-left layout and per-content text direction in a real browser."""
from __future__ import annotations

from cookbook.models import Post, Recipe
from cookbook.site_pages import render_html, render_shopping_list_html

BASE = "http://cookbook.test"


def _recipe() -> Recipe:
    recipe = Recipe(
        id="r1", image_url="", caption="Salad", timestamp_utc="2026-08-24T12:00:00Z",
        title="Salad", recipe_url="", recipe_name="", source="lizapanelim",
    )
    recipe.post = Post(shortcode="r1", url="https://www.instagram.com/p/r1/", typename="GraphImage", is_video=False)
    return recipe


def _open(page, url: str) -> None:
    state = {
        "overrides": {
            "r1": {
                "id": "r1", "title": "Salad", "sourceUrl": "", "source": "lizapanelim",
                "recipeUrl": "", "recipeName": "", "recipeUrls": [], "recipeNames": [], "imageUrl": "",
                "ingredients": [
                    {"name": "Flour", "varieties": "", "amount": "1 cup"},
                    {"name": "קמח", "varieties": "", "amount": "כוס"},
                ],
                "instructions": "Mix well", "prerequisiteId": "", "notes": "",
            }
        },
        "custom": [],
    }
    page.route(f"{BASE}/api/recipe-state", lambda route: route.fulfill(json={"revision": 1, "state": state}))
    page.route(f"{BASE}/api/recipe-types", lambda route: route.fulfill(json=[]))
    page.route(f"{BASE}/api/import-post", lambda route: route.fulfill(json={"status": "idle", "message": ""}))
    page.route(f"{BASE}/index.html*", lambda route: route.fulfill(
        content_type="text/html", body=render_html([_recipe()], "example", "favicon.svg")))
    page.goto(url)
    page.locator("[data-recipe-id]").first.wait_for()


def _direction(page, selector: str) -> str:
    return page.locator(selector).first.evaluate("element => getComputedStyle(element).direction")


def test_page_flows_right_to_left(page) -> None:
    _open(page, f"{BASE}/index.html")

    assert _direction(page, "html") == "rtl"
    title = page.locator(".page-header h1").bounding_box()
    add_button = page.locator("#add-recipe").bounding_box()
    assert title["x"] > add_button["x"]  # The heading sits on the right, the actions on the left.


def test_recipe_content_takes_its_direction_from_its_own_text(page) -> None:
    _open(page, f"{BASE}/index.html?recipe=r1")

    assert _direction(page, ".card-title") == "ltr"  # English title
    assert _direction(page, ".ingredients-table tbody tr:nth-child(1) td:nth-child(1)") == "ltr"  # Flour
    assert _direction(page, ".ingredients-table tbody tr:nth-child(2) td:nth-child(1)") == "rtl"  # קמח
    assert _direction(page, ".recipe-instructions pre") == "ltr"  # Mix well
    assert _direction(page, ".recipe-ingredients h3") == "rtl"  # UI heading keeps the page direction
    assert _direction(page, "#source-url") == "ltr"  # URLs are always left to right


def test_shopping_item_names_are_isolated_from_the_page_direction(page) -> None:
    items = [{"id": "1", "name": "Eggs (12)", "done": False}, {"id": "2", "name": "חלב", "done": False}]
    page.route(f"{BASE}/api/shopping-list", lambda route: route.fulfill(json={"items": items, "revision": 1}))
    page.route(f"{BASE}/shopping_list.html", lambda route: route.fulfill(
        content_type="text/html", body=render_shopping_list_html("favicon.svg")))
    page.goto(f"{BASE}/shopping_list.html")
    page.wait_for_function("!document.getElementById('shopping-item-input').disabled")

    assert _direction(page, ".shopping-item label") == "rtl"  # The row keeps the page direction...
    assert _direction(page, ".shopping-item label bdi >> nth=0") == "rtl"  # חלב sorts first
    assert page.locator(".shopping-item label bdi").all_inner_texts() == ["חלב", "Eggs (12)"]
    assert _direction(page, ".shopping-item:nth-child(2) label bdi") == "ltr"  # ...but each name uses its own.
