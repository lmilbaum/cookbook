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
      <h1>Liora's cookbook</h1>
      <p class="link-row"><a href="shopping_list.html">Open shopping list</a></p>
      <section class=\"grid\">
{cards_markup}
      </section>
    </main>
  </body>
</html>
"""


def render_shopping_list_html(favicon_href: str) -> str:
    """Render the standalone shopping-list page using the report's shared storage."""

    safe_favicon_href = html.escape(favicon_href, quote=True)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Shopping list</title>
    <link rel="icon" type="image/svg+xml" href="{safe_favicon_href}" />
    <style>
      body {{ margin: 0; background: #0f1115; color: #eceef3; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
      main {{ max-width: 680px; margin: 0 auto; padding: 32px 16px 48px; }}
      .back-link {{ color: #8db7ff; }}
      .shopping-list {{ background: #f4efe6; color: #24211d; border: 1px solid #d8cbb8; border-radius: 12px; padding: 20px; margin-top: 24px; }}
      h1 {{ margin: 0; }}
      h2 {{ margin: 0 0 14px; }}
      .shopping-form {{ display: flex; gap: 8px; margin-bottom: 14px; }}
      input[type="text"] {{ min-width: 0; flex: 1; border: 1px solid #b9aa96; border-radius: 6px; padding: 10px 12px; font: inherit; }}
      .shopping-form button, .clear-purchased {{ border: 0; border-radius: 6px; padding: 10px 14px; background: #24211d; color: #fffaf2; font: inherit; cursor: pointer; }}
      .shopping-items {{ display: grid; gap: 6px; margin-bottom: 14px; }}
      .shopping-item {{ display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #dfd4c5; }}
      .shopping-item label {{ flex: 1; overflow-wrap: anywhere; }}
      .shopping-item.done label {{ color: #83796d; text-decoration: line-through; }}
      .remove-item {{ border: 0; background: transparent; color: #9a3d35; cursor: pointer; }}
      .empty-shopping-list {{ color: #756b60; }}
      .list-footer {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
      @media (max-width: 480px) {{ .shopping-form {{ flex-wrap: wrap; }} .shopping-form button {{ flex: 1; }} }}
    </style>
  </head>
  <body>
    <main>
      <a class="back-link" href="lizapanelim_posts.html">Back to cookbook</a>
      <section class="shopping-list" aria-labelledby="shopping-list-title">
        <h1 id="shopping-list-title">Shopping list</h1>
        <p>Add items, check them off, and keep the list in this browser.</p>
        <form class="shopping-form" id="shopping-form">
          <input id="shopping-item-input" type="text" maxlength="120" placeholder="Add an item..." aria-label="Shopping list item" required />
          <button type="submit">Add item</button>
        </form>
        <div class="shopping-items" id="shopping-items"></div>
        <p class="empty-shopping-list" id="empty-shopping-list">Your list is empty.</p>
        <div class="list-footer">
          <span id="shopping-count">0 items</span>
          <button class="clear-purchased" id="clear-purchased" type="button">Clear purchased</button>
        </div>
      </section>
    </main>
    <script>
      (() => {{
        const storageKey = "cookbook-shopping-list";
        const form = document.getElementById("shopping-form");
        const input = document.getElementById("shopping-item-input");
        const itemsElement = document.getElementById("shopping-items");
        const emptyElement = document.getElementById("empty-shopping-list");
        const countElement = document.getElementById("shopping-count");
        const clearButton = document.getElementById("clear-purchased");
        let items = JSON.parse(localStorage.getItem(storageKey) || "[]");
        const save = () => localStorage.setItem(storageKey, JSON.stringify(items));
        const render = () => {{
          itemsElement.replaceChildren();
          items.forEach((item) => {{
            const row = document.createElement("div");
            row.className = `shopping-item${{item.done ? " done" : ""}}`;
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = item.done;
            checkbox.setAttribute("aria-label", `Mark ${{item.name}} as purchased`);
            checkbox.addEventListener("change", () => {{ item.done = checkbox.checked; save(); render(); }});
            const label = document.createElement("label");
            label.textContent = item.name;
            const removeButton = document.createElement("button");
            removeButton.className = "remove-item";
            removeButton.type = "button";
            removeButton.textContent = "Remove";
            removeButton.addEventListener("click", () => {{ items = items.filter((candidate) => candidate.id !== item.id); save(); render(); }});
            row.append(checkbox, label, removeButton);
            itemsElement.append(row);
          }});
          emptyElement.hidden = items.length > 0;
          countElement.textContent = `${{items.length}} item${{items.length === 1 ? "" : "s"}}`;
        }};
        form.addEventListener("submit", (event) => {{
          event.preventDefault();
          const name = input.value.trim();
          if (!name) return;
          items.push({{ id: `${{Date.now()}}-${{Math.random()}}`, name, done: false }});
          save();
          input.value = "";
          render();
          input.focus();
        }});
        clearButton.addEventListener("click", () => {{ items = items.filter((item) => !item.done); save(); render(); }});
        render();
      }})();
    </script>
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
