"""Exercise the recipe-type combobox in a real browser against a mocked API."""
from __future__ import annotations

from cookbook.models import Post, Recipe
from cookbook.recipe_state_repository import valid_state
from cookbook.site_pages import render_html

BASE = "http://cookbook.test"


def _recipe() -> Recipe:
    recipe = Recipe(
        id="r1", image_url="", caption="Salad", timestamp_utc="2026-08-24T12:00:00Z",
        title="Salad", recipe_url="", recipe_name="", source="lizapanelim",
    )
    recipe.post = Post(shortcode="r1", url="https://www.instagram.com/p/r1/", typename="GraphImage", is_video=False)
    return recipe


def _open_recipe_page(page, existing_types):
    calls = {"types": [], "state_puts": []}
    types = [{"id": i + 1, "name": name} for i, name in enumerate(existing_types)]

    def recipe_types(route):
        if route.request.method == "POST":
            name = route.request.post_data_json["name"]
            calls["types"].append(name)
            types.append({"id": len(types) + 1, "name": name})
            route.fulfill(status=201, json=types[-1])
        else:
            route.fulfill(json=types)

    def recipe_state(route):
        if route.request.method == "PUT":
            calls["state_puts"].append(route.request.post_data_json)
            route.fulfill(json={"revision": 2})
        else:
            route.fulfill(json={"revision": 1, "state": {"overrides": {}, "custom": []}})

    page.route(f"{BASE}/api/recipe-types", recipe_types)
    page.route(f"{BASE}/api/recipe-state", recipe_state)
    page.route(f"{BASE}/api/import-post", lambda route: route.fulfill(json={"status": "idle", "message": ""}))
    page.route(f"{BASE}/index.html*", lambda route: route.fulfill(
        content_type="text/html", body=render_html([_recipe()], "example", "favicon.svg")))
    page.goto(f"{BASE}/index.html?recipe=r1")
    page.locator("#recipe-type").wait_for()
    return calls


def test_enter_creates_the_type_and_updates_the_recipe(page):
    calls = _open_recipe_page(page, ["עוגה"])
    field = page.locator("#recipe-type")
    assert field.input_value() == "לא ידוע"

    field.fill("מרק")
    assert page.locator("#recipe-type-list li.new").inner_text() == 'הוספת "מרק"'
    field.press("Enter")

    page.wait_for_function("document.getElementById('save-status').textContent !== ''")
    assert calls["types"] == ["מרק"]
    assert field.input_value() == "מרק"
    assert page.locator("#recipe-type-list").is_hidden()
    assert page.locator("#recipe-title").input_value() == "Salad"  # Enter did not submit or reset the form
    saved = calls["state_puts"][-1]["state"]["overrides"]["r1"]
    assert saved["type"] == "מרק"
    # Regression: the real server rejected recipes carrying a `source` field, so the type never
    # persisted. Whatever the page sends must pass the server's validation.
    assert valid_state(calls["state_puts"][-1]["state"])
    assert "מרק" in page.locator("#search-type option").all_inner_texts()


def test_choosing_an_existing_type_does_not_create_a_duplicate(page):
    calls = _open_recipe_page(page, ["עוגה", "סלט"])
    page.locator("#recipe-type").click()
    assert page.locator("#recipe-type-list li").all_inner_texts() == ["סלט", "עוגה", "לא ידוע"]
    page.locator("#recipe-type-list li", has_text="סלט").click()

    page.wait_for_function("document.getElementById('save-status').textContent !== ''")
    assert calls["types"] == []
    assert page.locator("#recipe-type").input_value() == "סלט"
    assert calls["state_puts"][-1]["state"]["overrides"]["r1"]["type"] == "סלט"


def test_arrow_keys_and_enter_pick_a_filtered_type(page):
    calls = _open_recipe_page(page, ["עוגה", "עוגיות", "סלט"])
    field = page.locator("#recipe-type")
    field.fill("עוג")
    assert page.locator("#recipe-type-list li").all_inner_texts() == ["עוגה", "עוגיות", 'הוספת "עוג"']
    field.press("ArrowDown")
    field.press("ArrowDown")
    field.press("Enter")

    page.wait_for_function("document.getElementById('save-status').textContent !== ''")
    assert field.input_value() == "עוגיות"
    assert calls["types"] == []


def test_all_recipes_show_initially_and_filters_update_immediately(page):
    other = Recipe(
        id="r2", image_url="", caption="Jam", timestamp_utc="2026-08-25T12:00:00Z",
        title="Jam", recipe_url="https://example.com/jam", recipe_name="Jam", source="unknown",
    )
    _open_recipe_page(page, ["עוגה"])
    page.route(f"{BASE}/index.html*", lambda route: route.fulfill(
        content_type="text/html", body=render_html([_recipe(), other], "example", "favicon.svg")))
    page.goto(f"{BASE}/index.html")
    page.locator("#recipe-search").wait_for()
    assert page.get_by_role("button", name="חיפוש").count() == 0
    assert page.locator("[data-recipe-id]:visible").count() == 2
    assert page.locator("#no-filter-results").is_hidden()

    page.select_option("#search-source", "unknown")
    assert page.locator("[data-recipe-id]:visible").count() == 1
    assert page.locator("#no-filter-results").is_hidden()

    page.select_option("#search-source", "lizapanelim")
    assert page.locator("[data-recipe-id]:visible").count() == 1

    page.select_option("#search-type", "עוגה")
    assert page.locator("[data-recipe-id]:visible").count() == 0
    page.select_option("#search-type", "לא ידוע")
    assert page.locator("[data-recipe-id]:visible").count() == 1


def test_a_type_set_on_the_recipe_page_finds_the_recipe_in_the_home_page_filter(page):
    """Regression: the new type appeared in the filter dropdown but the recipe was not found."""
    store = {"state": {"overrides": {}, "custom": []}, "revision": 1, "types": []}

    def recipe_types(route):
        if route.request.method == "POST":
            store["types"].append(route.request.post_data_json["name"])
            route.fulfill(status=201, json={"id": len(store["types"]), "name": store["types"][-1]})
        else:
            route.fulfill(json=[{"id": i, "name": name} for i, name in enumerate(store["types"])])

    def recipe_state(route):
        if route.request.method == "PUT":
            body = route.request.post_data_json
            if not valid_state(body["state"]):  # mirror the server, which answers 400
                route.fulfill(status=400, json={"error": "Invalid recipe state"})
                return
            store["state"], store["revision"] = body["state"], store["revision"] + 1
            route.fulfill(json={"revision": store["revision"]})
        else:
            route.fulfill(json={"revision": store["revision"], "state": store["state"]})

    page.route(f"{BASE}/api/recipe-types", recipe_types)
    page.route(f"{BASE}/api/recipe-state", recipe_state)
    page.route(f"{BASE}/api/import-post", lambda route: route.fulfill(json={"status": "idle", "message": ""}))
    page.route(f"{BASE}/index.html*", lambda route: route.fulfill(
        content_type="text/html", body=render_html([_recipe()], "example", "favicon.svg")))

    page.goto(f"{BASE}/index.html?recipe=r1")
    page.locator("#recipe-type").fill("מרק")
    page.locator("#recipe-type").press("Enter")
    page.wait_for_function("document.getElementById('save-status').textContent !== ''")

    page.goto(f"{BASE}/index.html")
    page.locator("#search-type").wait_for()
    page.select_option("#search-type", "מרק")
    assert page.locator("[data-recipe-id]:visible").count() == 1


def test_source_filter_uses_unknown_for_recipes_from_other_sites(page):
    """The filter option and the stored source are both "unknown"."""
    other = Recipe(
        id="r2", image_url="", caption="Jam", timestamp_utc="2026-08-25T12:00:00Z",
        title="Jam", recipe_url="https://example.com/jam", recipe_name="Jam", source="unknown",
    )
    _open_recipe_page(page, [])
    page.route(f"{BASE}/index.html*", lambda route: route.fulfill(
        content_type="text/html", body=render_html([_recipe(), other], "example", "favicon.svg")))
    page.goto(f"{BASE}/index.html")
    page.locator("#search-source").wait_for()

    options = page.locator("#search-source option")
    assert options.evaluate_all("els => els.map(e => e.value)") == ["", "lizapanelim", "unknown"]
    assert "אחר" not in options.all_inner_texts()

    page.select_option("#search-source", "unknown")
    assert page.locator("[data-recipe-id]:visible").evaluate_all("els => els.map(e => e.dataset.recipeId)") == ["r2"]
    page.select_option("#search-source", "lizapanelim")
    assert page.locator("[data-recipe-id]:visible").evaluate_all("els => els.map(e => e.dataset.recipeId)") == ["r1"]


def test_saving_existing_custom_instagram_recipe_triggers_import_and_updates_source(page):
    """Regression: a custom-... entry with an Instagram URL must re-import on save,
    replacing the custom id with the real shortcode and setting the correct source profile."""
    custom_id = "custom-1234567890-abc"
    current_state = [{"overrides": {}, "custom": [{
        "id": custom_id, "title": "Reel Recipe", "source": "unknown",
        "sourceUrl": "https://www.instagram.com/reel/SomeShortcode/",
        "recipeUrl": "", "recipeName": "", "recipeUrls": [], "recipeNames": [],
        "imageUrl": "", "ingredients": [], "instructions": "",
        "type": "לא ידוע", "prerequisiteId": "", "notes": "",
    }], "order": [custom_id]}]
    import_calls = []

    def recipe_state(route):
        if route.request.method == "PUT":
            current_state[0] = route.request.post_data_json["state"]
            route.fulfill(json={"revision": 2})
        else:
            route.fulfill(json={"revision": 1, "state": current_state[0]})

    def do_import(route):
        import_calls.append(route.request.post_data_json)
        route.fulfill(json={"id": "SomeShortcode", "source": "otherchef"})

    _open_recipe_page(page, [])
    page.route(f"{BASE}/api/recipe-state", recipe_state)
    page.route(f"{BASE}/api/import-instagram-url", do_import)
    page.route(f"{BASE}/index.html*", lambda route: route.fulfill(
        content_type="text/html", body=render_html([_recipe()], "example", "favicon.svg")))
    page.goto(f"{BASE}/index.html?recipe={custom_id}")
    page.locator("#recipe-title").wait_for()
    assert page.locator("#recipe-title").input_value() == "Reel Recipe"

    with page.expect_navigation(timeout=8000):
        page.locator("#recipe-form button[type=submit]").click()

    assert import_calls == [{"url": "https://www.instagram.com/reel/SomeShortcode/"}]
    saved = current_state[0]
    assert not any(r["id"] == custom_id for r in saved.get("custom", []))
    assert "SomeShortcode" in saved.get("overrides", {})
    assert saved["overrides"]["SomeShortcode"]["source"] == "otherchef"
