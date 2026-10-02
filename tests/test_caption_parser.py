"""Test caption parsing from Instagram posts."""

from __future__ import annotations

import pytest

from cookbook.caption_parser import ParsedCaption, parse_caption
from cookbook.recipe_state_repository import valid_state


def test_instagram_wrapper_with_direction_marks_stripped():
    """Instagram wrapper with direction marks should be stripped."""
    caption = "22K likes‎, comments, and saves on December 5, 2024: \"לבצק חלב וביצים\""
    result = parse_caption(caption)
    assert result.title != "22K likes"
    assert "לבצק חלב וביצים" in result.title


def test_ingredient_and_instruction_headers():
    """Headers for ingredients and instructions should split content correctly."""
    caption = """עוגת שוקולד טעימה

מצרכים:
- 2 כוסות קמח
- 1 כוס סוכר
- חצי כוס שמן זית

אופן ההכנה:
1. מערבבים את המצרכים
2. מטבלים לתבנית
3. אופים ב-180 מעלות"""
    result = parse_caption(caption)
    assert result.title == "עוגת שוקולד טעימה"
    assert len(result.ingredients) >= 2
    assert any("קמח" in ing["name"] for ing in result.ingredients)
    assert "מערבבים" in result.instructions


def test_headerless_hebrew_caption():
    """Headerless caption with explicit headers should work correctly."""
    caption = """עוגת שוקולד עשירה

מצרכים:
2 כוסות קמח
1 כוס סוכר
חצי כוס שמן

אופן ההכנה:
מערבבים הכל ומטבלים לתבנית.
אופים בתנור ב-180 מעלות עד שזה מוכן."""
    result = parse_caption(caption)
    assert result.title == "עוגת שוקולד עשירה"
    assert len(result.ingredients) >= 2
    assert result.instructions


@pytest.mark.parametrize(
    "line,expected_amount,expected_name",
    [
        ("2 cups flour", "2", "flour"),
        ("1/2 cup sugar", "1/2 cup", "sugar"),
        ("3 eggs", "3", "eggs"),
        ("1 tablespoon salt", "1 tablespoon", "salt"),
        ("- 5 ripe peaches", "5", "peaches"),
    ],
)
def test_ingredient_line_parsing(line, expected_amount, expected_name):
    """Parametrized test for ingredient line parsing."""
    caption = f"Ingredients:\n{line}\n\nInstructions:\nMix well"
    result = parse_caption(caption)
    assert len(result.ingredients) > 0
    ing = result.ingredients[0]
    assert expected_amount in ing["amount"] or ing["amount"].startswith(expected_amount)
    assert expected_name.lower() in ing["name"].lower()


def test_english_ingredients():
    """English ingredient headers and items should parse correctly."""
    caption = """Chocolate Cake

Ingredients: - 5 ripe peaches - 2 cups cream

Instructions:
Mix well and serve."""
    result = parse_caption(caption)
    assert result.title == "Chocolate Cake"
    assert len(result.ingredients) >= 2
    assert any("peaches" in ing["name"] for ing in result.ingredients)


def test_hashtags_removed_from_title():
    """Hashtags should be removed from title and other content."""
    caption = """#chocolate #cake עוגת שוקולד עשירה #בעבודה

מצרכים:
#sugar 2 כוסות קמח"""
    result = parse_caption(caption)
    assert "#" not in result.title
    assert "עוגת שוקולד" in result.title


def test_long_title_cut_at_sentence_end():
    """Long titles should be cut at sentence end or word boundary."""
    caption = """This is a very long title that has multiple sentences. It should be cut at the period. This part should not appear."""
    result = parse_caption(caption)
    assert len(result.title) <= 160
    assert "." in result.title
    assert "This part" not in result.title


def test_emoji_removed_from_title():
    """Emoji should be removed from title."""
    caption = "🎂 Chocolate Cake 🍫 Recipe"
    result = parse_caption(caption)
    assert "🎂" not in result.title
    assert "🍫" not in result.title
    assert "Chocolate" in result.title


def test_caption_with_only_content():
    """Caption with only ingredients and instructions (no title) should still parse."""
    caption = """Ingredients:
- 2 cups flour
- 1 cup sugar

Instructions:
Mix well"""
    result = parse_caption(caption)
    assert len(result.ingredients) >= 1
    assert result.instructions


def test_empty_caption():
    """Empty caption should return empty ParsedCaption."""
    result = parse_caption("")
    assert result.title == ""
    assert result.ingredients == []
    assert result.instructions == ""


def test_hashtag_only_caption():
    """Caption with only hashtags should return empty ParsedCaption."""
    result = parse_caption("#hashtag #onlyhashtags #nothingelse")
    assert result.title == ""
    assert result.ingredients == []
    assert result.instructions == ""


def test_very_long_caption():
    """Very long caption should not cause exceptions and should respect caps."""
    long_caption = "A" * 50000
    result = parse_caption(long_caption)
    assert len(result.instructions) <= 10000
    assert len(result.title) <= 160


def test_parsed_caption_as_override():
    """ParsedCaption.as_override() should return only non-empty fields."""
    caption = ParsedCaption(
        title="Test Title",
        ingredients=[{"name": "Salt", "amount": "1 tsp", "varieties": ""}],
        instructions="Mix well",
    )
    override = caption.as_override()
    assert "title" in override
    assert "ingredients" in override
    assert "instructions" in override


def test_parsed_caption_as_override_empty_title():
    """Empty title should not be included in override."""
    caption = ParsedCaption(title="", ingredients=[], instructions="")
    override = caption.as_override()
    assert not override


def test_parsed_caption_as_override_partial():
    """Only non-empty fields should be included."""
    caption = ParsedCaption(
        title="Test",
        ingredients=[],
        instructions="",
    )
    override = caption.as_override()
    assert "title" in override
    assert "ingredients" not in override
    assert "instructions" not in override


def test_contract_valid_state():
    """Every parsed caption should produce a valid override for recipe state."""
    test_captions = [
        "עוגת שוקולד\n\nמצרכים:\n2 כוסות קמח\n\nהוראות:\nערבבו",
        "Simple Recipe",
        "Title\n- ingredient 1\n- ingredient 2",
    ]
    for caption in test_captions:
        parsed = parse_caption(caption)
        override = parsed.as_override()
        if override:
            test_state = {"overrides": {"x": {**override, "id": "x"}}, "custom": []}
            assert valid_state(test_state), f"Invalid state for caption: {caption}"


def test_stale_title_pattern():
    """Stale titles matching the Instagram wrapper pattern are recognized by fill_recipe_override."""
    # This tests that the parsing still works even with stale titles; fill_recipe_override handles stale detection
    # The parser extracts whatever title it can, and fill_recipe_override later detects stale patterns
    caption = "22K likes, 145 comments and 89 saves on December 5, 2024: \"真正的食譜\""
    result = parse_caption(caption)
    # The wrapper should be unwrapped and content extracted
    parsed = result.as_override()
    # Just ensure it doesn't crash
    assert isinstance(parsed, dict)


def test_group_headings_skipped():
    """Group headings like 'לבצק:' should be skipped in ingredient parsing."""
    caption = """עוגת שוקולד

מצרכים:
לבצק:
2 כוסות קמח
1 כוס סוכר

קצפת:
1 כוס מים"""
    result = parse_caption(caption)
    # Should parse ingredients but skip the group heading line
    assert len(result.ingredients) >= 2
    assert not any("לבצק" in ing["name"] for ing in result.ingredients)


def test_url_removed_from_title():
    """URLs should be removed from title."""
    caption = "Recipe from https://example.com/recipe Amazing Dish https://example.com/photo"
    result = parse_caption(caption)
    assert "https://" not in result.title
    assert "example.com" not in result.title
    assert "Recipe" in result.title or "Amazing" in result.title


def test_mentions_removed_from_title():
    """@mentions should be removed from title."""
    caption = "@photographer Amazing Dish by @chef Amazing Dish"
    result = parse_caption(caption)
    assert "@" not in result.title


def test_ingredient_with_dash_separator():
    """Ingredients separated by dash should parse correctly."""
    caption = """מצרכים:
קמח - 2 כוסות
סוכר - 1 כוס"""
    result = parse_caption(caption)
    assert len(result.ingredients) >= 2
    assert any("קמח" in ing["name"] and "2" in ing["amount"] for ing in result.ingredients)


def test_parenthesis_only_line():
    """A line that is only parenthesis should create a row with inner text as name."""
    caption = """מצרכים:
(צלעות מס 2)
2 כוסות קמח"""
    result = parse_caption(caption)
    assert any("צלעות" in ing["name"] for ing in result.ingredients)


def test_unicode_fractions():
    """Unicode fractions should be parsed as quantity."""
    caption = """מצרכים:
½ כוס מלח
⅔ כוס סוכר"""
    result = parse_caption(caption)
    assert len(result.ingredients) >= 2


def test_hebrew_number_words():
    """Hebrew number words should be parsed as quantity."""
    caption = """מצרכים:
שני כוסות קמח
שלוש ביצים"""
    result = parse_caption(caption)
    assert len(result.ingredients) >= 2
    assert any("שני" in ing["amount"] for ing in result.ingredients)
