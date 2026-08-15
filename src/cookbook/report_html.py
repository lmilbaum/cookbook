"""HTML report rendering and related assets."""

from __future__ import annotations

import html
from pathlib import Path

from .models import PostRecord

_ANTIPASTI_URL = (
    "https://www.thekitchencoach.co.il/"
    "%d7%9e%d7%aa%d7%9b%d7%95%d7%9f-%d7%90%d7%a0%d7%98%d7%99%d7%a4%d7%a1"
    "%d7%98%d7%99-%d7%99%d7%a8%d7%a7%d7%95%d7%aa-%d7%91%d7%aa%d7%a0%d7%95"
    "%d7%a8/"
)
_PIE_URL = "https://www.carine.co.il/foody_recipe/%d7%a4%d7%90%d7%99-%d7%aa%d7%a4%d7%95%d7%97%d7%99%d7%9d-%d7%90%d7%9e%d7%a8%d7%99%d7%a7%d7%90%d7%99/"
_AVOCADO_URL = "https://lizapanelim.com/%D7%A1%D7%9C%D7%98-%D7%90%D7%91%D7%95%D7%A7%D7%93%D7%95-%D7%90%D7%91%D7%99%D7%91%D7%99-%D7%9E%D7%A8%D7%A2%D7%A0%D7%9F/"


def _related_recipe_for_card(index: int) -> tuple[str, str]:
    """Return the related recipe URL and label for a card index."""

    if index == 3:
        return _AVOCADO_URL, "סלט אבוקדו אביבי מרענן - לייזה פאנלים"
    if index == 2:
        return _PIE_URL, "פאי תפוחים אמריקאי - Carine"
    return _ANTIPASTI_URL, "איך להכין אנטיפסטי - המדריך של עז תלם"


def _card_name_for_index(index: int) -> str:
    """Return the display title for each card by position."""

    if index == 1:
        return "אנטיפסטי"
    if index == 2:
        return "פאי תפוחים אמריקאי"
    return ""


def render_html(posts: list[PostRecord], username: str, favicon_href: str) -> str:
    """Render fetched posts into a standalone HTML document."""

    cards: list[str] = []
    for index, post in enumerate(posts, start=1):
        recipe_url, recipe_label = _related_recipe_for_card(index)
        card_name = _card_name_for_index(index)

        title_markup = ""
        if card_name:
            title_markup = f'<h2 class="card-title">{html.escape(card_name)}</h2>'

        img_markup = ""
        if post.image_url:
            safe_image_url = html.escape(post.image_url, quote=True)
            image_tag = (
                f'<img src="{safe_image_url}" alt="Instagram media preview" '
                'loading="lazy" />'
            )
            img_markup = (
                f'<a href="{recipe_url}" target="_blank" rel="noreferrer">'
                f"{image_tag}</a>"
            )

        related_recipe_markup = (
            '<p class="link-row" dir="rtl">'
            'מתכון קשור: '
            f'<a href="{recipe_url}" target="_blank" rel="noreferrer">'
            f'<bdi>{html.escape(recipe_label)}</bdi></a>'
            '</p>'
        )

        cards.append(
            f"""
      <article class=\"card\">
        {title_markup}
        <div class=\"meta\">
          <span>{html.escape(post.timestamp_utc)}</span>
          <span>Likes: {post.likes}</span>
          <span>Comments: {post.comments}</span>
          <span>{html.escape(post.typename)}</span>
        </div>
        <p class=\"link-row\">
          <a href=\"{html.escape(post.url, quote=True)}\" target=\"_blank\" rel=\"noreferrer\">
            Open on Instagram
          </a>
        </p>
        {related_recipe_markup}
        {img_markup}
        <pre>{html.escape(post.caption)}</pre>
      </article>
"""
        )

    cards_markup = "\n".join(cards) if cards else "<p>No posts found.</p>"
    safe_username = html.escape(username)
    safe_favicon_href = html.escape(favicon_href, quote=True)

    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>{safe_username} Instagram Posts</title>
    <link rel=\"icon\" type=\"image/svg+xml\" href=\"{safe_favicon_href}\" />
    <style>
      body {{
        margin: 0;
        font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif;
        background: #0f1115;
        color: #eceef3;
      }}
      main {{
        max-width: 980px;
        margin: 0 auto;
        padding: 24px 16px 48px;
      }}
      h1 {{
        margin: 0 0 8px;
      }}
      .subtitle {{
        margin: 0 0 24px;
        color: #b5bcc9;
      }}
      .link-row {{
        margin: 0 0 10px;
      }}
      .grid {{
        display: grid;
        gap: 16px;
      }}
      .card {{
        background: #171a21;
        border: 1px solid #2a2f3a;
        border-radius: 12px;
        padding: 16px;
      }}
      .card-title {{
        margin: 0 0 10px;
        font-size: 1.2rem;
        line-height: 1.25;
      }}
      img {{
        display: block;
        width: 100%;
        max-height: 640px;
        object-fit: contain;
        border-radius: 10px;
        margin: 0 0 14px;
        background: #101218;
      }}
      .meta {{
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        font-size: 0.9rem;
        color: #b5bcc9;
        margin-bottom: 10px;
      }}
      a {{
        color: #8db7ff;
      }}
      pre {{
        white-space: pre-wrap;
        word-break: break-word;
        margin: 0;
        font-family: inherit;
        line-height: 1.45;
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>@{safe_username}</h1>
      <p class=\"subtitle\">Fetched Instagram posts</p>
      <section class=\"grid\">
{cards_markup}
      </section>
    </main>
  </body>
</html>
"""


def write_favicon(output_path: Path) -> Path:
    """Write an SVG favicon next to the output files."""

    favicon_path = output_path.with_name("favicon.svg")
    favicon_svg = """<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 64 64\">
  <defs>
    <linearGradient id=\"ig\" x1=\"0%\" y1=\"100%\" x2=\"100%\" y2=\"0%\">
      <stop offset=\"0%\" stop-color=\"#f58529\"/>
      <stop offset=\"45%\" stop-color=\"#dd2a7b\"/>
      <stop offset=\"100%\" stop-color=\"#515bd4\"/>
    </linearGradient>
  </defs>
  <rect x=\"2\" y=\"2\" width=\"60\" height=\"60\" rx=\"16\" fill=\"url(#ig)\"/>
  <circle cx=\"32\" cy=\"32\" r=\"13\" fill=\"none\" stroke=\"white\" stroke-width=\"5\"/>
  <circle cx=\"46\" cy=\"18\" r=\"3.5\" fill=\"white\"/>
</svg>
"""
    favicon_path.write_text(favicon_svg, encoding="utf-8")
    return favicon_path
