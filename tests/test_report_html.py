"""Unit tests for cookbook HTML report rendering."""

from __future__ import annotations

import json
import unittest

from cookbook.models import Post, Recipe
from cookbook.report_html import (
    _recipe_name_from_url,
    _title_for_recipe,
    render_html,
    render_notes_html,
    render_shopping_list_html,
)


def make_recipe(**overrides: object) -> Recipe:
    """Build a representative recipe (with an attached post), allowing fields to be replaced."""

    values: dict[str, object] = {
        "id": "recipe-1",
        "url": "https://www.instagram.com/p/recipe-1/",
        "image_url": "https://images.example/recipe.jpg",
        "caption": "Caption title\nMore details",
        "timestamp_utc": "2026-08-24T12:00:00Z",
        "typename": "GraphImage",
        "is_video": False,
        "title": "Saved title",
        "recipe_url": "https://recipes.example/primary",
        "recipe_name": "",
        "source": "lizapanelim",
    }
    values.update(overrides)
    recipe_id = values.pop("id")
    url = values.pop("url")
    typename = values.pop("typename")
    is_video = values.pop("is_video")
    recipe = Recipe(id=recipe_id, **values)  # type: ignore[arg-type]
    if url:
        recipe.post = Post(shortcode=recipe_id, url=url, typename=typename, is_video=is_video)
    return recipe


class RecipeDataTests(unittest.TestCase):
    def test_recipe_name_is_derived_from_encoded_url_slug(self) -> None:
        self.assertEqual(
            _recipe_name_from_url(
                "https://example.com/%D7%A4%D7%90%D7%99-%D7%AA%D7%A4%D7%95%D7%97%D7%99%D7%9D/"
            ),
            "פאי תפוחים",
        )

    def test_title_precedence_is_item_sidecar_caption_then_empty(self) -> None:
        self.assertEqual(
            _title_for_recipe(make_recipe(title=" Item title "), {"recipe-1": "Sidecar"}),
            "Item title",
        )
        self.assertEqual(
            _title_for_recipe(make_recipe(title=""), {"recipe-1": " Sidecar title "}),
            "Sidecar title",
        )
        self.assertEqual(
            _title_for_recipe(make_recipe(title="", caption="\n Caption title \nBody"), {}),
            "Caption title",
        )
        self.assertEqual(_title_for_recipe(make_recipe(title="", caption=" \n "), {}), "")


class RenderHtmlTests(unittest.TestCase):
    def test_renders_base_recipe_data_as_json(self) -> None:
        recipe = make_recipe(
            id='recipe"<&',
            title='Pasta "special" <hot>',
            image_url="https://images.example/item?a=1&b=2",
        )

        document = render_html([recipe], "user", "favicon.svg")
        expected_data = json.dumps(
            {
                "id": recipe.id,
                "title": recipe.title,
                "sourceUrl": recipe.post.url,
                "source": recipe.source,
                "recipeUrl": recipe.recipe_url,
                "recipeName": "primary",
                "recipeUrls": [recipe.recipe_url],
                "recipeNames": ["primary"],
                "imageUrl": recipe.image_url,
                "ingredients": [],
                "instructions": "",
                "prerequisiteId": "",
                "notes": "",
            },
            ensure_ascii=False,
        )
        expected_script_data = expected_data.replace("<", "\\u003c")

        self.assertIn(f"const baseRecipes = [{expected_script_data}]", document)
        self.assertNotIn('<hot>', document)

    def test_blank_recipe_url_yields_no_recipe_links(self) -> None:
        document = render_html([make_recipe(recipe_url="")], "user", "favicon.svg")

        self.assertIn('"recipeUrl": "", "recipeName": "", "recipeUrls": [], "recipeNames": []', document)

    def test_renders_recipe_editor_controls_and_persistence_wiring(self) -> None:
        document = render_html([make_recipe()], "user", "favicon.svg")

        for fragment in (
            'id="add-recipe"',
            'id="recipe-dialog"',
            'id="recipe-form"',
            'id="recipe-title"',
            'id="recipe-url"',
            'id="source-url"',
            'id="image-url"',
            'id="ingredients-editor-body"',
            'id="add-ingredient"',
            'id="recipe-instructions"',
            'id="delete-recipe"',
            'class="edit-recipe"',
            'const storageKey = "cookbook-recipe-changes-v1"',
            "localStorage.setItem(hosted ? backupKey : storageKey, JSON.stringify(snapshot))",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, document)

        self.assertIn('ingredients: [...ingredientsEditorBody.rows].map', document)
        self.assertIn('instructions: instructionsInput.value.trim()', document)
        self.assertIn('<table class="ingredients-table"><thead><tr><th scope="col">שם</th><th scope="col">זנים מועדפים</th><th scope="col">כמות</th>', document)
        self.assertIn('const normalizeIngredients = (value)', document)
        self.assertIn('const addIngredientRow = (ingredient = {})', document)
        self.assertIn('cell.textContent = value', document)
        self.assertIn('ingredientsBox.hidden = false', document)
        self.assertIn(': [{ name: "", varieties: "", amount: "" }]', document)
        self.assertIn(r'.split(/\r?\n/)', document)
        self.assertIn('<section class="recipe-notes"><h3>הערות</h3><textarea aria-label="הערות למתכון"></textarea>', document)
        self.assertIn('.edit-recipe { display: block; margin: 0 0 10px auto; padding: 0; background: transparent; color: #8db7ff;', document)
        self.assertIn('<h3>הוראות הכנה</h3><pre></pre>', document)
        self.assertIn('<span>דרוש הכנה של</span><select aria-label="דרוש הכנה של">', document)
        self.assertIn('class="prerequisite-link">למתכון</a>', document)
        self.assertIn('`index.html?recipe=${encodeURIComponent(prerequisiteSelect.value)}`', document)
        self.assertIn('.recipe-prerequisite { display: flex; align-items: center;', document)
        self.assertIn('event.target.closest(".recipe-prerequisite select")', document)
        self.assertIn('prerequisiteId: select.value', document)

    def test_recipe_link_shows_the_linked_recipe_name(self) -> None:
        document = render_html(
            [make_recipe(recipe_url="https://example.com/roasted-vegetables/")],
            "user",
            "favicon.svg",
        )

        self.assertIn('"recipeName": "roasted vegetables"', document)
        self.assertIn(".recipe-links { display: grid; gap: 5px;", document)
        self.assertIn('class="card-meta" aria-label="קישורים למתכון"', document)
        self.assertIn(".recipe-notes { margin: 14px 0;", document)

    def test_recipe_link_prefers_the_page_title_when_available(self) -> None:
        document = render_html(
            [
                make_recipe(
                    recipe_url="https://example.com/avocado-salad/",
                    recipe_name="סלט אבוקדו הכל וסלט סלק לזלול!",
                )
            ],
            "user",
            "favicon.svg",
        )

        self.assertIn('"recipeName": "סלט אבוקדו הכל וסלט סלק לזלול!"', document)
        self.assertIn('const target = `cookbook-recipe-${recipe.id}', document)

    def test_each_recipe_links_to_its_own_notes_page(self) -> None:
        cookbook = render_html([make_recipe()], "user", "favicon.svg")
        notes = render_notes_html([make_recipe()], "favicon.svg")

        self.assertIn('event.target.closest(".recipe-notes textarea")', cookbook)
        self.assertIn('notes: notes.value', cookbook)
        self.assertNotIn('id="recipe-notes"', cookbook)
        self.assertIn('const scrollStorageKey = "cookbook-main-scroll-position"', cookbook)
        self.assertIn("window.scrollTo(0, Number(savedScrollPosition) || 0)", cookbook)
        self.assertIn("<title>Recipe notes</title>", notes)
        self.assertIn('class="notes-grid"', notes)
        self.assertIn('new URLSearchParams(window.location.search).get("id")', notes)
        self.assertIn('candidate.id === recipeId', notes)
        self.assertIn('input.dir = "rtl"', notes)
        self.assertIn('localStorage.setItem(hosted ? backupKey : storageKey, JSON.stringify(snapshot))', notes)

    def test_renders_empty_title_element_so_existing_card_can_be_edited(self) -> None:
        document = render_html([make_recipe(title="", caption="")], "user", "favicon.svg")

        self.assertIn('<header class="card-header"><h2 class="card-title" dir="auto"><a class="recipe-detail-link"></a></h2>', document)
        self.assertIn('"id": "recipe-1", "title": ""', document)

    def test_main_cards_link_to_a_dedicated_recipe_view(self) -> None:
        document = render_html([make_recipe()], "user", "favicon.svg")

        self.assertIn('document.body.classList.add(selectedRecipeId ? "recipe-view" : "cookbook-view")', document)
        self.assertIn('.cookbook-view .recipe-ingredients,', document)
        self.assertIn('.recipe-view .card-image a { width: min(220px, 100%); }', document)
        self.assertIn('.recipe-view .recipe-form { margin-top: 16px;', document)
        self.assertIn('const detailUrl = `index.html?recipe=${encodeURIComponent(recipe.id)}`', document)
        self.assertIn('card.hidden = card.dataset.recipeId !== selectedRecipeId', document)
        self.assertIn('selectedCard.append(form)', document)
        self.assertIn('openEditor(recipeFromCard(selectedCard), !baseIds.has(selectedRecipeId), true)', document)

    def test_existing_and_custom_recipes_use_the_same_card_factory(self) -> None:
        document = render_html([make_recipe()], "user", "favicon.svg")

        self.assertIn("const recipesById = new Map(allRecipes()", document)
        self.assertIn("state.order.forEach((id) => grid.append(createCard(recipesById.get(id))))", document)

    def test_new_recipes_are_appended_to_the_shared_collection_order(self) -> None:
        document = render_html([make_recipe()], "user", "favicon.svg")

        self.assertIn("if (!state.order.includes(recipe.id)) state.order.push(recipe.id)", document)
        self.assertIn("else grid.append(createCard(recipe))", document)

    def test_custom_recipe_link_uses_the_entered_title_not_the_url_filename(self) -> None:
        document = render_html([make_recipe()], "user", "favicon.svg")

        self.assertIn("index === 0 && !baseIds.has(recipe.id)", document)
        self.assertIn("const recipeName = isCustomRecipe", document)
        self.assertIn("? title", document)

    def test_empty_report_still_contains_add_recipe_interface(self) -> None:
        document = render_html([], "user", "favicon.svg")

        self.assertIn("<p>No posts found.</p>", document)
        self.assertIn('id="add-recipe"', document)
        self.assertIn('id="recipe-dialog"', document)

    def test_shopping_list_link_stays_available_while_scrolling(self) -> None:
        document = render_html([make_recipe()], "user", "favicon.svg")

        self.assertIn('class="shopping-list-link" href="shopping_list.html"', document)
        self.assertIn(".shopping-list-link {", document)
        self.assertIn("position: fixed;", document)

    def test_file_image_links_are_mapped_to_http_assets_after_migration(self) -> None:
        document = render_html([make_recipe()], "user", "favicon.svg")

        self.assertIn('url.protocol === "file:" && window.location.protocol.startsWith("http")', document)
        self.assertIn('["/lizapanelim_posts_assets/", "/recipes/"]', document)
        self.assertIn("`${window.location.origin}${url.pathname.slice", document)

    def test_renders_source_filter_for_liza_panelim_and_other(self) -> None:
        document = render_html([make_recipe()], "user", "favicon.svg")

        self.assertIn('id="source-filter"', document)
        self.assertIn('id="filter-lizapanelim" checked /> ליזה פאנלים', document)
        self.assertIn('id="filter-other" checked /> אחר', document)
        self.assertIn('id="no-filter-results"', document)
        self.assertIn(".recipe-view .source-filter { display: none; }", document)
        self.assertIn('sourceFilter.addEventListener("change", applySourceFilter)', document)
        self.assertIn('recipeFromCard(card).source === "lizapanelim" ? showLiza : showOther', document)

    def test_base_recipe_source_is_passed_through_from_the_recipe_unchanged(self) -> None:
        document = render_html(
            [make_recipe(id="other-site-recipe", source="other")],
            "user",
            "favicon.svg",
        )

        self.assertIn('"id": "other-site-recipe", "title": "Saved title", "sourceUrl": "https://www.instagram.com/p/recipe-1/", "source": "other"', document)

    def test_custom_recipes_default_to_the_other_source_bucket(self) -> None:
        document = render_html([make_recipe()], "user", "favicon.svg")

        self.assertIn('openEditor({ id: "", title: "", recipeUrl: "", sourceUrl: "", imageUrl: "", ingredients: [], instructions: "", prerequisiteId: "", notes: "", source: "other" }, true)', document)
        self.assertIn('source: previous.source || "other"', document)

    def test_shopping_list_displays_items_alphabetically(self) -> None:
        document = render_shopping_list_html("favicon.svg")
        self.assertIn('a.name.localeCompare(b.name, "he")', document)

    def test_shopping_list_can_be_sent_to_trello(self) -> None:
        document = render_shopping_list_html("favicon.svg")

        self.assertNotIn('id="share-list"', document)
        self.assertIn('id="send-to-trello"', document)
        self.assertIn('<span>ייצוא ל־</span><bdi>Trello</bdi>', document)
        self.assertNotIn("navigator.share", document)
        self.assertIn('fetch("/api/trello/cards"', document)
        self.assertIn('setBidiStatus(statusText, "My To Do List", ". ")', document)
        self.assertIn('setBidiStatus("מייצא את רשימת הקניות ל־", "Trello", "…")', document)
        self.assertNotIn("https://trello.com/add-card?", document)
        self.assertIn('fetch("/api/shopping-list"', document)
        self.assertIn('method: "PUT"', document)


if __name__ == "__main__":
    unittest.main()


def test_recipe_save_feedback_is_local_and_temporary() -> None:
    cookbook = render_html([make_recipe()], "user", "favicon.svg")
    notes = render_notes_html([make_recipe()], "favicon.svg")
    for document in (cookbook, notes):
        assert 'report("Saved.", true)' in document
        assert 'clearTimeout(target.saveTimer)' in document
        assert 'statusVersions.get(target) === version' in document
        assert 'persistenceStatus.hidden = true' in document
        assert 'Saved to database.' not in document
    assert 'save(card.querySelector(".recipe-notes-status"))' in cookbook
    assert 'save(card.querySelector(".prerequisite-status"))' in cookbook
    assert 'const saved = save(saveStatus)' in cookbook
    assert 'if (!await saved) return' in cookbook
    assert 'grid.append(createCard(recipesById.get(id))));\n        save();' not in cookbook
    assert 'save(status)' in notes
