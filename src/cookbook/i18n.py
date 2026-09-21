"""User-interface strings for the generated pages, keyed by locale.

Only UI chrome lives here. Recipe titles, ingredients, notes and other user
data are stored and rendered in whatever language they were written in.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_LOCALE = "he"

_HEBREW: dict[str, str] = {
    "app_title": "ספר המתכונים שלי",
    "saved": "נשמר.",
    "saving": "שומר…",
    # Cookbook page.
    "add_recipe": "הוסף מתכון",
    "add_recipe_title": "הוספת מתכון",
    "edit_recipe": "עריכת המתכון",
    "import_next_post": "ייבוא הפוסט הבא מהסוף",
    "import_starting": "מתחיל ייבוא…",
    "import_running": "מחפש את הפוסט הישן ביותר שעדיין לא יובא. זה עשוי לקחת כמה דקות.",
    "import_succeeded": "הפוסט יובא. רעננו את ספר המתכונים כדי לראות אותו.",
    "import_empty": "לא נמצאו פוסטים חדשים בסוף הפיד שנטען.",
    "import_incomplete": "לא ניתן היה לסיים את הסריקה של הפוסט הישן ביותר. לא יובא אף פוסט. נסו שוב מאוחר יותר.",
    "import_incomplete_reason": "לא ניתן היה לסיים את הסריקה של הפוסט הישן ביותר. לא יובא אף פוסט. סיבה: {reason} נסו שוב מאוחר יותר.",
    "import_failed": "הייבוא נכשל. בדקו את פרטי ההתחברות והגישה לאינסטגרם ונסו שוב.",
    "import_timeout": "הייבוא חרג ממגבלת הזמן. נסו שוב מאוחר יותר.",
    "import_error": "לא ניתן היה לסיים את הייבוא. רעננו את ספר המתכונים לפני שתנסו שוב.",
    "import_reason_pagination_incomplete": "נתוני העימוד של הפרופיל היו חלקיים; לא נבחר פוסט.",
    "import_reason_pagination_unconfirmed": "אינסטגרם לא אישרה את סוף העימוד של הפרופיל; לא נבחר פוסט.",
    "import_reason_scroll_limit": "הגלילה בפרופיל הגיעה למגבלת הבטיחות; לא נבחר פוסט.",
    "import_reason_feed_end_not_found": "הגלילה בפרופיל הגיעה למגבלת הבטיחות לפני שנמצא סוף הפיד; לא נבחר פוסט.",
    "import_status_unavailable": "לא ניתן לבדוק את מצב הייבוא. מתחבר מחדש…",
    "import_refresh": "רענון ספר המתכונים",
    "back_to_all_recipes": "חזרה לכל המתכונים",
    "shopping_list": "רשימת הקניות",
    "shopping_list_open": "פתיחת רשימת הקניות",
    "search_recipes": "חיפוש מתכונים",
    "filter_type": "סוג",
    "filter_source": "מקור",
    "filter_all": "הכל",
    "source_lizapanelim": "ליזה פאנלים",
    "source_unknown": "לא ידוע",
    "no_filter_results": "אין מתכונים התואמים לסינון.",
    "no_recipes": "לא נמצאו מתכונים.",
    "recipe_name": "שם המתכון",
    "recipe_type": "סוג מתכון",
    "recipe_type_placeholder": "בחרו סוג או הקלידו סוג חדש ולחצו Enter",
    "recipe_types": "סוגי מתכונים",
    "type_add": 'הוספת "{name}"',
    "recipe_link": "קישור למתכון",
    "source_link": "קישור למקור",
    "image_link": "קישור לתמונה",
    "ingredients": "מצרכים",
    "ingredient_name": "שם",
    "ingredient_varieties": "זנים מועדפים",
    "ingredient_amount": "כמות",
    "ingredient_actions": "פעולות",
    "add_ingredient": "הוספת מצרך",
    "remove_ingredient": "מחיקת מצרך",
    "instructions": "הוראות הכנה",
    "instructions_placeholder": "הקלידו כאן את הוראות ההכנה...",
    "not_recipe": "לא מתכון",
    "delete": "מחיקה",
    "cancel": "ביטול",
    "save": "שמירה",
    "recipe_links": "קישורים למתכון",
    "recipes": "מתכונים",
    "prerequisite": "דרוש הכנה של",
    "to_recipe": "למתכון",
    "no_prerequisite": "לא נדרש מתכון נוסף",
    "notes": "הערות",
    "recipe_notes": "הערות למתכון",
    "instagram": "אינסטגרם",
    "recipe_details": "פרטי המתכון: {title}",
    "marking_not_recipe": "מסמן כלא מתכון…",
    "mark_failed": "לא ניתן לסמן את הפוסט. נסו שוב.",
    "recipes_reload_blocked": "יש לרענן את הדף לפני שמירה נוספת. גיבוי הדפדפן נשמר.",
    "recipes_conflict": "המתכונים שונו בלשונית אחרת. יש לרענן את הדף לפני השמירה. גיבוי הדפדפן נשמר.",
    "recipes_save_failed": "השמירה במסד הנתונים נכשלה. גיבוי הדפדפן נשמר. יש לרענן את הדף ולנסות שוב.",
    "recipes_load_failed": "לא ניתן לטעון את המתכונים. יש לרענן את הדף ולנסות שוב; נתוני הדפדפן נשמרו.",
    "recipes_browser_save_failed": "לא ניתן לשמור בדפדפן זה.",
    "recipes_save_unrecoverable": "השמירה נכשלה וגיבוי הדפדפן אינו זמין. השאירו את הדף פתוח והעתיקו את השינויים.",
    # Notes page.
    "back_to_cookbook": "חזרה לספר המתכונים",
    "notes_intro": "ההערות נשמרות אוטומטית.",
    "recipe_not_found": "המתכון לא נמצא",
    "open_notes_hint": "יש לפתוח הערות מכרטיס מתכון בספר המתכונים.",
    "notes_document_title": "{title} – הערות",
    "recipe_fallback": "מתכון",
    "untitled_recipe": "מתכון ללא שם",
    "notes_placeholder": "הוסיפו טיפים להכנה, תחליפים או הערות נוספות...",
    # Shopping-list page.
    "shopping_intro": "הוסיפו פריטים, סמנו אותם כשנקנו, והרשימה תישמר בדפדפן זה.",
    "shopping_placeholder": "הוסיפו פריט...",
    "shopping_item": "פריט ברשימת הקניות",
    "add_item": "הוספת פריט",
    "list_empty": "הרשימה ריקה.",
    "items_count_one": "פריט אחד",
    "items_count_other": "{count} פריטים",
    "clear_purchased": "ניקוי פריטים שנקנו",
    "export_shopping_list": "ייצוא רשימת הקניות",
    "mark_purchased": "סימון {name} כנקנה",
    "remove": "הסרה",
    "export_to": "ייצוא ל־",
    "exporting_to": "מייצא את רשימת הקניות ל־",
    "export_updated": "הכרטיס הקיים עודכן בבורד ",
    "export_created": "כרטיס חדש נוצר בבורד ",
    "open_card": "פתיחת הכרטיס",
    "export_failed_to": "לא ניתן היה לייצא את הרשימה ל־",
    "export_failed": "הייצוא ל־Trello נכשל",
    "shopping_reload_blocked": "יש לרענן את הדף לפני שמירה נוספת; גיבוי הדפדפן נשמר.",
    "shopping_conflict": "רשימת הקניות שונתה בלשונית אחרת. יש לרענן את הדף לפני השמירה; גיבוי הדפדפן נשמר.",
    "shopping_save_failed": "השמירה במסד הנתונים נכשלה. יש לרענן את הדף ולנסות שוב; גיבוי הדפדפן נשמר.",
    "shopping_browser_save_failed": "השמירה בדפדפן נכשלה. השאירו את הדף פתוח והעתיקו את הרשימה.",
    "shopping_save_unrecoverable": "השמירה נכשלה וגיבוי הדפדפן אינו זמין. השאירו את הדף פתוח והעתיקו את הרשימה.",
    "shopping_load_failed": "לא ניתן לטעון את רשימת הקניות. יש לרענן את הדף ולנסות שוב; נתוני הדפדפן נשמרו.",
}

_ENGLISH: dict[str, str] = {
    "app_title": "My cookbook",
    "saved": "Saved.",
    "saving": "Saving…",
    # Cookbook page.
    "add_recipe": "Add recipe",
    "add_recipe_title": "Add recipe",
    "edit_recipe": "Edit recipe",
    "import_next_post": "Import next post from the end",
    "import_starting": "Starting import…",
    "import_running": "Finding the oldest post not yet imported. This may take several minutes.",
    "import_succeeded": "Post imported. Refresh the cookbook to view it.",
    "import_empty": "No unseen posts were found at the end of the loaded feed.",
    "import_incomplete": "Could not finish scanning for the oldest post. No post was imported. Please try again later.",
    "import_incomplete_reason": "Could not finish scanning for the oldest post. No post was imported. Reason: {reason} Please try again later.",
    "import_failed": "Import failed. Check Instagram credentials and session access, then try again.",
    "import_timeout": "Import timed out. Please try again later.",
    "import_error": "Unable to finish the import. Refresh the cookbook before retrying.",
    "import_reason_pagination_incomplete": "Profile pagination data was incomplete; no post selected.",
    "import_reason_pagination_unconfirmed": "Instagram did not confirm the profile pagination end; no post selected.",
    "import_reason_scroll_limit": "Profile scrolling reached its safety limit; no post selected.",
    "import_reason_feed_end_not_found": "Profile scrolling reached its safety limit before finding the feed end; no post selected.",
    "import_status_unavailable": "Unable to check import status. Reconnecting…",
    "import_refresh": "Refresh cookbook",
    "back_to_all_recipes": "Back to all recipes",
    "shopping_list": "Shopping list",
    "shopping_list_open": "Open the shopping list",
    "search_recipes": "Search recipes",
    "filter_type": "Type",
    "filter_source": "Source",
    "filter_all": "All",
    "source_lizapanelim": "Liza Panelim",
    "source_unknown": "Unknown",
    "no_filter_results": "No recipes match the filter.",
    "no_recipes": "No recipes found.",
    "recipe_name": "Recipe name",
    "recipe_type": "Recipe type",
    "recipe_type_placeholder": "Choose a type, or type a new one and press Enter",
    "recipe_types": "Recipe types",
    "type_add": 'Add "{name}"',
    "recipe_link": "Recipe link",
    "source_link": "Source link",
    "image_link": "Image link",
    "ingredients": "Ingredients",
    "ingredient_name": "Name",
    "ingredient_varieties": "Preferred varieties",
    "ingredient_amount": "Amount",
    "ingredient_actions": "Actions",
    "add_ingredient": "Add ingredient",
    "remove_ingredient": "Remove ingredient",
    "instructions": "Instructions",
    "instructions_placeholder": "Type the instructions here...",
    "not_recipe": "Not a recipe",
    "delete": "Delete",
    "cancel": "Cancel",
    "save": "Save",
    "recipe_links": "Recipe links",
    "recipes": "Recipes",
    "prerequisite": "Requires preparing",
    "to_recipe": "Go to recipe",
    "no_prerequisite": "No other recipe required",
    "notes": "Notes",
    "recipe_notes": "Recipe notes",
    "instagram": "Instagram",
    "recipe_details": "Recipe details: {title}",
    "marking_not_recipe": "Marking as not a recipe…",
    "mark_failed": "Unable to mark the post. Try again.",
    "recipes_reload_blocked": "Reload before saving again. Your browser backup is retained.",
    "recipes_conflict": "Recipes changed in another tab. Reload before saving. Your browser backup is retained.",
    "recipes_save_failed": "Database save failed. Your browser backup is retained. Reload to retry.",
    "recipes_load_failed": "Unable to load recipes. Reload to retry; browser data is retained.",
    "recipes_browser_save_failed": "Unable to save in this browser.",
    "recipes_save_unrecoverable": "Save failed and browser backup is unavailable. Keep this page open and copy your edits.",
    # Notes page.
    "back_to_cookbook": "Back to cookbook",
    "notes_intro": "Notes are saved automatically.",
    "recipe_not_found": "Recipe not found",
    "open_notes_hint": "Open notes from a recipe card in the cookbook.",
    "notes_document_title": "{title} notes",
    "recipe_fallback": "Recipe",
    "untitled_recipe": "Untitled recipe",
    "notes_placeholder": "Add preparation tips, substitutions or other notes...",
    # Shopping-list page.
    "shopping_intro": "Add items, check them off, and keep the list in this browser.",
    "shopping_placeholder": "Add an item...",
    "shopping_item": "Shopping list item",
    "add_item": "Add item",
    "list_empty": "Your list is empty.",
    "items_count_one": "1 item",
    "items_count_other": "{count} items",
    "clear_purchased": "Clear purchased",
    "export_shopping_list": "Export shopping list",
    "mark_purchased": "Mark {name} as purchased",
    "remove": "Remove",
    "export_to": "Export to ",
    "exporting_to": "Exporting the shopping list to ",
    "export_updated": "The existing card was updated on the board ",
    "export_created": "A new card was created on the board ",
    "open_card": "Open the card",
    "export_failed_to": "Unable to export the list to ",
    "export_failed": "Trello export failed",
    "shopping_reload_blocked": "Reload before saving again; your browser backup is retained.",
    "shopping_conflict": "Shopping list changed in another tab. Reload before saving; your browser backup is retained.",
    "shopping_save_failed": "Database save failed. Reload to retry; your browser backup is retained.",
    "shopping_browser_save_failed": "Browser save failed. Keep this page open and copy your list.",
    "shopping_save_unrecoverable": "Save failed and browser backup is unavailable. Keep this page open and copy your list.",
    "shopping_load_failed": "Unable to load shopping list. Reload to retry; browser data is retained.",
}


@dataclass(frozen=True)
class _Locale:
    direction: str
    strings: Mapping[str, str]


LOCALES: dict[str, _Locale] = {
    "he": _Locale(direction="rtl", strings=_HEBREW),
    "en": _Locale(direction="ltr", strings=_ENGLISH),
}

# Marks a string in a static script: @@key@@ becomes a JavaScript string literal.
_SCRIPT_MARKER = re.compile(r"@@([a-z_]+)@@")


class Translator:
    """Look up UI strings for one locale, escaped for the context they land in."""

    def __init__(self, locale: str = DEFAULT_LOCALE) -> None:
        if locale not in LOCALES:
            raise ValueError(f"Unsupported locale {locale!r}; expected one of {sorted(LOCALES)}.")
        self.lang = locale
        self.direction = LOCALES[locale].direction
        self._strings = LOCALES[locale].strings

    def text(self, key: str) -> str:
        """Return the raw string; raises KeyError for an unknown key."""

        return self._strings[key]

    def html(self, key: str) -> str:
        """Return the string escaped for HTML text and attribute values."""

        return html.escape(self.text(key), quote=True)

    def js(self, key: str) -> str:
        """Return the string as a JavaScript string literal, safe inside <script>."""

        return json.dumps(self.text(key), ensure_ascii=False).replace("</", "<\\/")

    @property
    def lang_js(self) -> str:
        """The locale code as a JavaScript string literal, for locale-aware sorting."""

        return json.dumps(self.lang)

    def fill(self, script: str) -> str:
        """Replace every @@key@@ marker in a static script with its string literal."""

        return _SCRIPT_MARKER.sub(lambda match: self.js(match.group(1)), script)
