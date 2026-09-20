"""Cover the UI string table and the language/direction of the rendered pages."""
from __future__ import annotations

import re

import pytest

from cookbook.i18n import DEFAULT_LOCALE, LOCALES, Translator
from cookbook.models import Post, Recipe
from cookbook.site_pages import render_html, render_notes_html, render_shopping_list_html


def _recipe() -> Recipe:
    recipe = Recipe(
        id="r1", image_url="", caption="Salad", timestamp_utc="2026-08-24T12:00:00Z",
        title="Salad", recipe_url="", recipe_name="", source="lizapanelim",
    )
    recipe.post = Post(shortcode="r1", url="https://www.instagram.com/p/r1/", typename="GraphImage", is_video=False)
    return recipe


def _pages(locale: str) -> dict[str, str]:
    return {
        "cookbook": render_html([_recipe()], "user", "favicon.svg", locale=locale),
        "notes": render_notes_html([_recipe()], "favicon.svg", locale=locale),
        "shopping": render_shopping_list_html("favicon.svg", locale=locale),
    }


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def test_default_locale_is_hebrew() -> None:
    assert DEFAULT_LOCALE == "he"
    assert 'lang="he" dir="rtl"' in render_shopping_list_html("favicon.svg")


def test_every_locale_defines_the_same_keys() -> None:
    reference = set(LOCALES[DEFAULT_LOCALE].strings)
    for code, locale in LOCALES.items():
        assert set(locale.strings) == reference, code


def test_placeholders_match_across_locales() -> None:
    reference = LOCALES[DEFAULT_LOCALE].strings
    for code, locale in LOCALES.items():
        for key, text in locale.strings.items():
            assert _placeholders(text) == _placeholders(reference[key]), (code, key)


@pytest.mark.parametrize("locale", sorted(LOCALES))
def test_every_page_renders_with_all_strings_resolved(locale: str) -> None:
    for name, document in _pages(locale).items():
        assert "@@" not in document, name


@pytest.mark.parametrize(("locale", "direction"), [("he", "rtl"), ("en", "ltr")])
def test_pages_declare_language_and_direction(locale: str, direction: str) -> None:
    for name, document in _pages(locale).items():
        assert f'<html lang="{locale}" dir="{direction}">' in document, name


def test_ui_strings_follow_the_selected_locale() -> None:
    hebrew, english = _pages("he"), _pages("en")
    assert ">הוסף מתכון</button>" in hebrew["cookbook"]
    assert ">Add recipe</button>" in english["cookbook"]
    assert "הוסף מתכון" not in english["cookbook"]
    assert ">שמירה</button>" in hebrew["cookbook"]
    assert ">Save</button>" in english["cookbook"]
    assert "<title>רשימת הקניות</title>" in hebrew["shopping"]
    assert "<title>Shopping list</title>" in english["shopping"]
    assert 'localeCompare(b.name, "en")' in english["shopping"]


def test_unknown_recipe_type_is_stored_data_and_not_localized() -> None:
    for locale in LOCALES:
        assert 'const unknownType = "לא ידוע";' in _pages(locale)["cookbook"]


def test_unsupported_locale_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported locale"):
        Translator("fr")
    with pytest.raises(ValueError, match="Unsupported locale"):
        render_shopping_list_html("favicon.svg", locale="fr")


def test_translator_escapes_for_the_context_it_is_used_in() -> None:
    translator = Translator("en")
    translator._strings = {"x": 'a "b" <c> </script>'}  # noqa: SLF001
    assert translator.html("x") == "a &quot;b&quot; &lt;c&gt; &lt;/script&gt;"
    assert translator.js("x") == '"a \\"b\\" <c> <\\/script>"'
    assert translator.fill("show(@@x@@)") == 'show("a \\"b\\" <c> <\\/script>")'
    with pytest.raises(KeyError):
        translator.text("missing")


def test_pages_inherit_direction_instead_of_hard_coding_it() -> None:
    for locale in LOCALES:
        for name, document in _pages(locale).items():
            document = re.sub(r"<html [^>]*>", "", document, count=1)  # Direction belongs on the root element only.
            for physical in ("direction: rtl", "text-align: right", "row-reverse", "margin-right", 'dir="rtl"'):
                assert physical not in document, (locale, name, physical)


def test_user_content_uses_automatic_direction() -> None:
    pages = _pages("he")
    cookbook = pages["cookbook"]
    for fragment in (
        '<pre dir="auto"></pre>',
        '<textarea dir="auto" aria-label="הערות למתכון"></textarea>',
        'cell.dir = "auto"',
        'input.dir = "auto"',
        'id="recipe-title" type="text" maxlength="160" dir="auto"',
        'id="recipe-instructions" maxlength="10000" dir="auto"',
        'id="recipe-type" type="text" role="combobox"',
    ):
        assert fragment in cookbook, fragment
    assert 'input.dir = "auto"' in pages["notes"]
    for field in ("recipe-url", "source-url", "image-url"):
        assert re.search(rf'id="{field}" type="(?:url|text)" dir="ltr"', cookbook), field
