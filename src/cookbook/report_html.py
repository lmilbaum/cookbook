"""HTML report rendering and related assets."""

from __future__ import annotations

import html
from pathlib import Path

from .models import PostRecord


def _recipe_urls_for_post(post: PostRecord) -> list[str]:
    """Return unique recipe URLs, supporting both old and new record formats."""

    urls = ([post.recipe_url] if post.recipe_url.strip() else []) + post.recipe_urls
    return list(dict.fromkeys(url.strip() for url in urls if url.strip()))


def _title_for_post(post: PostRecord, titles: dict[str, str]) -> str:
    """Prefer a user-provided title, then use the first caption line."""

    if post.title.strip():
        return post.title.strip()

    sidecar_title = titles.get(post.shortcode, "").strip()
    if sidecar_title:
        return sidecar_title

    caption_lines = [line.strip() for line in post.caption.splitlines() if line.strip()]
    return caption_lines[0] if caption_lines else ""


def render_html(
    posts: list[PostRecord],
    username: str,
    favicon_href: str,
    titles: dict[str, str] | None = None,
) -> str:
    """Render fetched posts into a standalone HTML document."""

    titles = titles or {}
    cards: list[str] = []
    for post in posts:
        title = _title_for_post(post, titles)
        title_markup = f'<h2 class="card-title">{html.escape(title)}</h2>' if title else ""

        img_markup = ""
        if post.image_url:
            safe_image_url = html.escape(post.image_url, quote=True)
            image_tag = (
                f'<img src="{safe_image_url}" alt="Instagram media preview" '
                'loading="lazy" />'
            )
            img_markup = (
                f'<a href="{html.escape(post.url, quote=True)}" target="_blank" rel="noreferrer">'
                f"{image_tag}</a>"
            )

        recipe_markup = "\n".join(
            '<p class="link-row">'
            '<a href="'
            f'{html.escape(recipe_url, quote=True)}'
            '" target="_blank" rel="noreferrer">'
            'Open recipe'
            '</a>'
            '</p>'
            for recipe_url in _recipe_urls_for_post(post)
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
        {recipe_markup}
        {img_markup}
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
