"""Unit tests for cookbook HTML report rendering."""

from __future__ import annotations

import html
import json
import unittest

from cookbook.models import PostRecord
from cookbook.report_html import (
    _recipe_name_from_url,
    _recipe_urls_for_post,
    _title_for_post,
    render_html,
    render_notes_html,
)


def make_post(**overrides: object) -> PostRecord:
    """Build a representative post, allowing individual fields to be replaced."""

    values: dict[str, object] = {
        "shortcode": "recipe-1",
        "url": "https://www.instagram.com/p/recipe-1/",
        "image_url": "https://images.example/recipe.jpg",
        "caption": "Caption title\nMore details",
        "timestamp_utc": "2026-08-24T12:00:00Z",
        "likes": 42,
        "comments": 7,
        "typename": "GraphImage",
        "is_video": False,
        "title": "Saved title",
        "recipe_url": "https://recipes.example/primary",
        "recipe_urls": ["https://recipes.example/secondary"],
    }
    values.update(overrides)
    return PostRecord(**values)  # type: ignore[arg-type]


class RecipeDataTests(unittest.TestCase):
    def test_recipe_name_is_derived_from_encoded_url_slug(self) -> None:
        self.assertEqual(
            _recipe_name_from_url(
                "https://example.com/%D7%A4%D7%90%D7%99-%D7%AA%D7%A4%D7%95%D7%97%D7%99%D7%9D/"
            ),
            "פאי תפוחים",
        )

    def test_recipe_urls_are_trimmed_deduplicated_and_ordered(self) -> None:
        post = make_post(
            recipe_url=" https://recipes.example/primary ",
            recipe_urls=[
                "https://recipes.example/primary",
                "",
                " https://recipes.example/secondary ",
            ],
        )

        self.assertEqual(
            _recipe_urls_for_post(post),
            [
                "https://recipes.example/primary",
                "https://recipes.example/secondary",
            ],
        )

    def test_title_precedence_is_record_sidecar_caption_then_empty(self) -> None:
        self.assertEqual(
            _title_for_post(make_post(title=" Record title "), {"recipe-1": "Sidecar"}),
            "Record title",
        )
        self.assertEqual(
            _title_for_post(make_post(title=""), {"recipe-1": " Sidecar title "}),
            "Sidecar title",
        )
        self.assertEqual(
            _title_for_post(make_post(title="", caption="\n Caption title \nBody"), {}),
            "Caption title",
        )
        self.assertEqual(_title_for_post(make_post(title="", caption=" \n "), {}), "")


class RenderHtmlTests(unittest.TestCase):
    def test_renders_editor_data_as_escaped_json(self) -> None:
        post = make_post(
            shortcode='recipe"<&',
            title='Pasta "special" <hot>',
            url="https://source.example/item?a=1&b=2",
            image_url="https://images.example/item?a=1&b=2",
        )

        document = render_html([post], "user", "favicon.svg")
        expected_data = html.escape(
            json.dumps(
                {
                    "id": post.shortcode,
                    "title": post.title,
                    "sourceUrl": post.url,
                    "recipeUrl": post.recipe_url,
                    "recipeName": "primary",
                    "imageUrl": post.image_url,
                    "notes": "",
                },
                ensure_ascii=False,
            ),
            quote=True,
        )

        self.assertIn(f'data-recipe-id="{html.escape(post.shortcode, quote=True)}"', document)
        self.assertIn(f'data-recipe="{expected_data}"', document)
        self.assertIn("Pasta &quot;special&quot; &lt;hot&gt;", document)
        self.assertNotIn('<hot>', document)

    def test_renders_recipe_editor_controls_and_persistence_wiring(self) -> None:
        document = render_html([make_post()], "user", "favicon.svg")

        for fragment in (
            'id="add-recipe"',
            'id="recipe-dialog"',
            'id="recipe-form"',
            'id="recipe-title"',
            'id="recipe-url"',
            'id="source-url"',
            'id="image-url"',
            'id="delete-recipe"',
            'class="edit-recipe"',
            'const storageKey = "cookbook-recipe-changes-v1"',
            "localStorage.setItem(storageKey, JSON.stringify(state))",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, document)

    def test_recipe_link_shows_the_linked_recipe_name(self) -> None:
        document = render_html(
            [make_post(recipe_url="https://example.com/roasted-vegetables/")],
            "user",
            "favicon.svg",
        )

        self.assertIn(">roasted vegetables</a>", document)

    def test_recipe_link_prefers_the_page_title_when_available(self) -> None:
        document = render_html(
            [
                make_post(
                    recipe_url="https://example.com/avocado-salad/",
                    recipe_names=["סלט אבוקדו הכל וסלט סלק לזלול!"],
                )
            ],
            "user",
            "favicon.svg",
        )

        self.assertIn('dir="auto">סלט אבוקדו הכל וסלט סלק לזלול!</a>', document)
        self.assertIn('target="cookbook-recipe-recipe-1"', document)
        self.assertIn('"recipeName": "סלט אבוקדו הכל וסלט סלק לזלול!"', html.unescape(document))

    def test_each_recipe_links_to_its_own_notes_page(self) -> None:
        cookbook = render_html([make_post()], "user", "favicon.svg")
        notes = render_notes_html([make_post()], "favicon.svg")

        self.assertIn('href="notes.html?id=recipe-1"', cookbook)
        self.assertNotIn('id="recipe-notes"', cookbook)
        self.assertIn('const scrollStorageKey = "cookbook-main-scroll-position"', cookbook)
        self.assertIn("sessionStorage.setItem(scrollStorageKey, String(window.scrollY))", cookbook)
        self.assertIn("window.scrollTo(0, Number(savedScrollPosition) || 0)", cookbook)
        self.assertIn("<title>Recipe notes</title>", notes)
        self.assertIn('class="notes-grid"', notes)
        self.assertIn('new URLSearchParams(window.location.search).get("id")', notes)
        self.assertIn('candidate.id === recipeId', notes)
        self.assertIn('input.dir = "rtl"', notes)
        self.assertIn('localStorage.setItem(storageKey, JSON.stringify(state))', notes)

    def test_renders_empty_title_element_so_existing_card_can_be_edited(self) -> None:
        document = render_html([make_post(title="", caption="")], "user", "favicon.svg")

        self.assertIn('<h2 class="card-title" dir="auto"></h2>', document)
        self.assertIn('data-recipe-id="recipe-1"', document)

    def test_empty_report_still_contains_add_recipe_interface(self) -> None:
        document = render_html([], "user", "favicon.svg")

        self.assertIn("<p>No posts found.</p>", document)
        self.assertIn('id="add-recipe"', document)
        self.assertIn('id="recipe-dialog"', document)


if __name__ == "__main__":
    unittest.main()
