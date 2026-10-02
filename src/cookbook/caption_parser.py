"""Parse Instagram captions to extract recipe metadata."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


def _remove_emoji(text: str) -> str:
    """Remove emoji and variation selectors using unicodedata."""
    # Remove characters in So (Symbol, other), Sk (Symbol, modifier), variation selectors, and zero-width joiners
    result = []
    for char in text:
        category = unicodedata.category(char)
        # Skip emoji (So, Sk categories) and variation selectors (FE0F) and zero-width joiners (U+200D)
        if category in ("So", "Sk") or char in ("️", "‍"):
            continue
        result.append(char)
    return "".join(result)


@dataclass(frozen=True)
class ParsedCaption:
    """Recipe metadata extracted from an Instagram caption."""

    title: str
    ingredients: list[dict[str, str]]  # each: {name, amount, varieties}
    instructions: str

    def as_override(self) -> dict[str, Any]:
        """Return only non-empty fields (suitable for a state override patch)."""
        result = {}
        if self.title:
            result["title"] = self.title
        if self.ingredients:
            result["ingredients"] = self.ingredients
        if self.instructions:
            result["instructions"] = self.instructions
        return result


def _strip_unicode_marks(text: str) -> str:
    """Remove invisible Unicode direction/bidi marks and normalize quotes."""
    # Remove direction marks and bidi control characters
    marks_to_remove = {
        "‎",  # LEFT-TO-RIGHT MARK
        "‏",  # RIGHT-TO-LEFT MARK
        "‪",  # LEFT-TO-RIGHT EMBEDDING
        "‫",  # RIGHT-TO-LEFT EMBEDDING
        "‬",  # POP DIRECTIONAL FORMATTING
        "‭",  # LEFT-TO-RIGHT OVERRIDE
        "‮",  # RIGHT-TO-LEFT OVERRIDE
        "⁦",  # LEFT-TO-RIGHT ISOLATE
        "⁧",  # RIGHT-TO-LEFT ISOLATE
        "⁨",  # FIRST STRONG ISOLATE
        "⁩",  # POP DIRECTIONAL ISOLATE
        "﻿",  # ZERO WIDTH NO-BREAK SPACE
    }
    result = "".join(c for c in text if c not in marks_to_remove)
    # Normalize quotes
    result = result.replace("״", '"').replace("″", '"')  # ״ and ″ to "
    return result


def _unwrap_instagram_wrapper(text: str) -> str:
    """Unwrap Instagram og:description wrapper if present."""
    pattern = r'[\d.,]+[KkMm]?\s*likes?,.*?:\s+"(?P<body>.*)"\.?\s*$'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group("body")
    return text


def _remove_hashtags_and_filter_lines(text: str) -> list[str]:
    """Remove hashtags and filter out empty/URL-only lines."""
    lines = []
    for line in text.splitlines():
        # Remove hashtags
        line = re.sub(r"#\w+", "", line)
        line = line.strip()

        # Skip empty lines and URL-only lines
        if not line or re.match(r"^https?://", line):
            continue

        lines.append(line)
    return lines


def _is_header(text: str) -> tuple[bool, list[str]]:
    """
    Check if a line is a header. Returns (is_header, items_after_colon).

    Items after ':' on header lines are split on ' - ', ' * ', ' • ', etc.
    """
    ingredient_keywords = {
        "מצרכים",
        "המצרכים",
        "מרכיבים",
        "רכיבים",
        "חומרים",
        "החומרים",
        "מה צריך",
        "ingredients",
        "you'll need",
        "you will need",
        "what you need",
    }
    instruction_keywords = {
        "אופן ההכנה",
        "אופן הכנה",
        "הכנה",
        "ההכנה",
        "הוראות הכנה",
        "הוראות",
        "שלבי הכנה",
        "שלבי ההכנה",
        "דרך ההכנה",
        "איך מכינים",
        "instructions",
        "method",
        "directions",
        "preparation",
        "steps",
        "how to make",
    }

    # Strip emoji, bullets, and header punctuation
    normalized = _remove_emoji(text)
    normalized = re.sub(r"^[\s\-•*–:]+", "", normalized)  # leading bullets/punctuation
    normalized = re.sub(r"[\s\-•*–:]+$", "", normalized)  # trailing
    normalized_lower = normalized.lower()

    all_keywords = ingredient_keywords | instruction_keywords
    for keyword in all_keywords:
        if normalized_lower == keyword or normalized_lower.startswith(keyword.lower()):
            # Extract items after colon if present
            colon_idx = text.find(":")
            if colon_idx != -1:
                after_colon = text[colon_idx + 1 :].strip()
                items = re.split(r"\s[-•*–]\s", after_colon)
                items = [item.strip() for item in items if item.strip()]
                return True, items
            return True, []
    return False, []


def _is_strong_ingredient_line(line: str) -> bool:
    """Check if a line starts with a quantity token or bullet."""
    # Remove leading bullets and emoji
    stripped = _remove_emoji(line)
    stripped = re.sub(r"^[\s\-•*–]+", "", stripped)

    # Check for leading number patterns
    quantity_patterns = [
        r"^\d+([.,/]\d+)?",  # numbers: 2, 2.5, 2/3
        r"^[½⅓⅔¼¾⅛]",  # Unicode fractions
        r"^\d+[½⅓⅔¼¾⅛]",  # mixed: 1½
        r"^(חצי|רבע|שליש|אחד|אחת|שני|שתי|שניים|שתיים|שלוש|שלושה|שלושת|שלושה|ארבע|ארבעה|ארבעת|חמש|חמישה|שש|שישה|שבע|שבעה|שמונה|תשע|תשעה|עשר|עשרה)",  # Hebrew numbers
    ]
    for pattern in quantity_patterns:
        if re.search(pattern, stripped):
            return True
    return False


def _extract_trailing_parenthesis(line: str) -> tuple[str, str]:
    """Extract trailing (…) as varieties, return (line_without_paren, varieties)."""
    match = re.search(r"\s*\((.+?)\)\s*$", line)
    if match:
        varieties = match.group(1)
        line = line[: match.start()]
        return line.rstrip(), varieties
    return line, ""


def _parse_quantity(text: str) -> str:
    """Extract a quantity from the start of text, including unit words and modifiers."""
    if not text:
        return ""

    # Hebrew and English units
    units = r"(?:כוס|כוסות|כף|כפות|כפית|כפיות|גרם|גר'|ג'|ק\"ג|קילו|קג|מ\"ל|מל|ליטר|יחידה|יחידות|חבילה|חבילות|שקית|שקיות|קופסה|קופסת|פחית|צרור|שן|שיני|ענף|ענפי|קורט|חופן|פרוסה|פרוסות|מקל|מקלות|אגודה|נתח|cup|cups|c|tbsp|tablespoon|tablespoons|tsp|teaspoon|teaspoons|g|gr|gram|grams|kg|ml|l|liter|liters|litre|litres|oz|ounce|ounces|lb|lbs|pound|pounds|pinch|clove|cloves|can|cans|package|packages|stick|sticks|slice|slices|handful)"

    # Number patterns
    numbers = r"(?:\d+(?:[.,/]\d+)?(?:½|⅓|⅔|¼|¾|⅛)?|[½⅓⅔¼¾⅛]|\d+[½⅓⅔¼¾⅛])"
    hebrew_numbers = r"(?:חצי|רבע|שליש|אחד|אחת|שני|שתי|שניים|שתיים|שלוש|שלושה|שלושת|ארבע|ארבעה|ארבעת|חמש|חמישה|שש|שישה|שבע|שבעה|שמונה|תשע|תשעה|עשר|עשרה)"

    # Try pattern: number/fraction + optional units + optional וחצי/ורבע + optional של
    pattern1 = rf"^(?:{numbers})(?:\s+{units})?(?:\s+(?:וחצי|ורבע))?(?:\s+של)?"
    match = re.match(pattern1, text, re.IGNORECASE)
    if match:
        return match.group(0).strip()

    # Try pattern: Hebrew number + optional units + optional וחצי/ורבע + optional של
    pattern2 = rf"^(?:{hebrew_numbers})(?:\s+{units})?(?:\s+(?:וחצי|ורבע))?(?:\s+של)?"
    match = re.match(pattern2, text, re.IGNORECASE)
    if match:
        return match.group(0).strip()

    # Fallback: check if text starts with just a unit word (e.g., "כוס וחצי חלב")
    pattern3 = rf"^{units}(?:\s+(?:וחצי|ורבע|של))?"
    match = re.match(pattern3, text, re.IGNORECASE)
    if match:
        return match.group(0).strip()

    return ""


def _parse_ingredient_line(line: str) -> dict[str, str]:
    """
    Parse a single ingredient line into {name, amount, varieties}.

    A line that is only parenthesis → its own row with inner text as name.
    """
    line = line.strip()

    # Handle parenthesis-only lines
    if re.match(r"^\s*\([^)]*\)\s*$", line):
        inner = re.sub(r"[()]+", "", line).strip()
        return {"name": inner[:120], "amount": "", "varieties": ""}

    # Strip leading bullets and emoji (but keep parenthesis for later)
    line = _remove_emoji(line)
    line = re.sub(r"^[\s\-•*–]+", "", line)

    # Strip ^\d+[.)]\s+ numbering only if what follows starts with a quantity
    match = re.match(r"^(\d+[.)]\s+)", line)
    if match:
        rest = line[len(match.group(1)) :]
        if _parse_quantity(rest):
            line = rest

    # Extract trailing (…) as varieties
    line, varieties = _extract_trailing_parenthesis(line)

    amount = ""
    name = line

    # Check for ` - QTY` or `: QTY` pattern
    dash_match = re.search(r"(.+?)\s*[-:]\s*(.+)$", line)
    if dash_match:
        potential_name = dash_match.group(1).strip()
        potential_amount = dash_match.group(2).strip()
        parsed_amount = _parse_quantity(potential_amount)
        if parsed_amount:
            name = potential_name
            amount = parsed_amount
        else:
            # No quantity after dash, treat whole line as name
            name = line
            amount = _parse_quantity(line)
            if amount:
                name = line[len(amount) :].strip()
    else:
        # Try to extract quantity from start
        amount = _parse_quantity(line)
        if amount:
            name = line[len(amount) :].strip()

    # Handle "לפי הטעם" / "לפי הצורך" / "to taste" / "as needed"
    if re.search(r"(לפי\s+(?:הטעם|הצורך)|to\s+taste|as\s+needed)", name, re.IGNORECASE):
        match = re.search(
            r"(לפי\s+(?:הטעם|הצורך)|to\s+taste|as\s+needed)",
            name,
            re.IGNORECASE,
        )
        if match:
            amount = match.group(0).strip()
            name = (name[: match.start()] + name[match.end() :]).strip()

    # Trim and cap
    name = name.strip()[:120]
    amount = amount.strip()[:120]
    varieties = varieties.strip()[:120]

    return {"name": name, "amount": amount, "varieties": varieties}


def _find_ingredient_block(lines: list[str]) -> tuple[int, int]:
    """
    Find the ingredient block as the first run of consecutive paragraphs where
    ≥50% of non-parenthesis-only lines are strong ingredient lines AND there are ≥2 such lines.

    Returns (start_idx, end_idx) indices in lines, or (-1, -1) if not found.
    For paragraph 0, exclude the first line (the title).
    """
    paragraphs: list[list[str]] = []
    current_para: list[str] = []

    for i, line in enumerate(lines):
        if i == 0:
            # Skip first line (title)
            continue
        if line.strip() == "":
            if current_para:
                paragraphs.append(current_para)
                current_para = []
        else:
            current_para.append(line)

    if current_para:
        paragraphs.append(current_para)

    # Find first run of consecutive paragraphs matching the ingredient block criteria
    for start_para in range(len(paragraphs)):
        strong_count = 0
        non_paren_count = 0

        for para_idx in range(start_para, len(paragraphs)):
            para = paragraphs[para_idx]

            # Check if any line is a short line ending in `:` with no digits (group heading)
            has_group_heading = any(
                re.match(r"^[^:]{1,20}:\s*$", line) and not any(c.isdigit() for c in line.split(":")[0])
                for line in para
            )
            if has_group_heading:
                # Stop at group headings
                break

            for line in para:
                # Skip group headings
                if re.match(r"^[^:]{1,20}:\s*$", line) and not any(
                    c.isdigit() for c in line.split(":")[0]
                ):
                    continue

                # Check if it's a parenthesis-only line
                if re.match(r"^\s*\([^)]*\)\s*$", line):
                    continue

                non_paren_count += 1
                if _is_strong_ingredient_line(line):
                    strong_count += 1

        # Check if this run meets the criteria
        if non_paren_count >= 2 and strong_count / non_paren_count >= 0.5:
            # Found the ingredient block
            # absolute start of the first ingredient paragraph in lines
            start_idx = sum(len(paragraphs[i]) + 1 for i in range(start_para))
            # absolute end: include paragraphs from start_para through para_idx
            end_idx = start_idx + sum(len(paragraphs[i]) + 1 for i in range(start_para, para_idx + 1))
            return start_idx, min(end_idx, len(lines))

    return -1, -1


def parse_caption(caption: str) -> ParsedCaption:
    """Parse an Instagram caption to extract recipe metadata."""
    # Step (a): Strip invisible marks
    caption = _strip_unicode_marks(caption)

    # Step (b): Unwrap Instagram wrapper
    caption = _unwrap_instagram_wrapper(caption)

    # Step (c): Remove hashtags and filter lines
    lines = _remove_hashtags_and_filter_lines(caption)

    if not lines:
        return ParsedCaption(title="", ingredients=[], instructions="")

    # Step (d): Detect headers
    ingredient_lines: list[str] = []
    instruction_lines: list[str] = []
    other_lines: list[str] = []

    current_section = "other"  # "ingredients", "instructions", or "other"

    for i, line in enumerate(lines):
        is_header, header_items = _is_header(line)
        if is_header:
            # Check if this is an ingredient or instruction header
            normalized = _remove_emoji(line)
            normalized = re.sub(r"^[\s\-•*–:]+", "", normalized)
            normalized_lower = normalized.lower()

            ingredient_keywords = {
                "מצרכים",
                "המצרכים",
                "מרכיבים",
                "רכיבים",
                "חומרים",
                "החומרים",
                "מה צריך",
                "ingredients",
                "you'll need",
                "you will need",
                "what you need",
            }
            instruction_keywords = {
                "אופן ההכנה",
                "אופן הכנה",
                "הכנה",
                "ההכנה",
                "הוראות הכנה",
                "הוראות",
                "שלבי הכנה",
                "שלבי ההכנה",
                "דרך ההכנה",
                "איך מכינים",
                "instructions",
                "method",
                "directions",
                "preparation",
                "steps",
                "how to make",
            }

            is_ingredient = any(kw in normalized_lower for kw in ingredient_keywords)
            is_instruction = any(kw in normalized_lower for kw in instruction_keywords)

            if is_ingredient:
                current_section = "ingredients"
                ingredient_lines.extend(header_items)
            elif is_instruction:
                current_section = "instructions"
                instruction_lines.extend(header_items)
            else:
                current_section = "other"
        else:
            # Not a header, add to current section
            if current_section == "ingredients":
                ingredient_lines.append(line)
            elif current_section == "instructions":
                instruction_lines.append(line)
            else:
                other_lines.append(line)

    # Step (e): Fallback if no headers found — use paragraph structure from original text.
    # _remove_hashtags_and_filter_lines strips blank lines, so we re-split the original
    # (post-unwrap, post-marks) text on double-newlines to recover paragraph boundaries.
    if not ingredient_lines and not instruction_lines:
        def _para_lines(raw: str) -> list[str]:
            result = []
            for l in raw.splitlines():
                l = re.sub(r"#\w+", "", l).strip()
                if l and not re.match(r"^https?://", l):
                    result.append(l)
            return result

        paras = [_para_lines(p) for p in re.split(r"\n{2,}", caption)]
        paras = [p for p in paras if p]

        block_idx = -1
        for i, para in enumerate(paras):
            candidates = [l for l in para if not re.match(r"^\s*\([^)]*\)\s*$", l)]
            if len(candidates) < 2:
                continue
            strong = sum(1 for l in candidates if _is_strong_ingredient_line(l))
            if strong / len(candidates) >= 0.5:
                block_idx = i
                break

        if block_idx != -1:
            ingredient_lines = paras[block_idx]
            for para in paras[block_idx + 1:]:
                if instruction_lines:
                    instruction_lines.append("")
                instruction_lines.extend(para)
        # When no block found: only the title is extracted; leave ingredients and instructions empty.

    # Step (f): Parse ingredient lines
    parsed_ingredients: list[dict[str, str]] = []
    for line in ingredient_lines:
        line = line.strip()
        if not line:
            continue

        # Skip group headings (short lines ending in ':' with no digits)
        if re.match(r"^[^:]{1,20}:\s*$", line) and not any(c.isdigit() for c in line.split(":")[0]):
            continue

        ingredient = _parse_ingredient_line(line)
        # Only add if name is not empty
        if ingredient["name"]:
            parsed_ingredients.append(ingredient)

    # Step (g): Instructions
    instructions = "\n".join(instruction_lines).strip()
    # Collapse runs of blank lines
    instructions = re.sub(r"\n\n+", "\n", instructions)
    instructions = instructions[:10000]

    # Step (h): Title
    title = ""
    for line in other_lines:
        if line.strip():
            title = line.strip()
            break

    if not title:
        # Use first line if no title found yet
        for line in lines:
            is_header, _ = _is_header(line)
            if not is_header:
                title = line.strip()
                break

    # Remove emoji, @mentions, URLs
    title = _remove_emoji(title)
    title = re.sub(r"@\w+", "", title)  # @mentions
    title = re.sub(r"https?://\S+", "", title)  # URLs
    title = re.sub(r"\s+", " ", title).strip()  # collapse whitespace

    # Trim leading/trailing quotes and punctuation
    title = re.sub(r'^["\'`\-–—\s]+', "", title)
    title = re.sub(r'["\'`\-–—\s]+$', "", title)

    # If longer than 80 chars, cut at first sentence end
    if len(title) > 80:
        match = re.search(r"[.!?…]", title)
        if match:
            title = title[: match.end()].strip()
            # Now try to fit within 80 chars at a word boundary
            if len(title) > 80:
                # Find word boundary before 80
                title = title[:80]
                last_space = title.rfind(" ")
                if last_space > 0:
                    title = title[:last_space]

    title = title[:160]

    return ParsedCaption(title=title, ingredients=parsed_ingredients, instructions=instructions)
