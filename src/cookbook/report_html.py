"""HTML report rendering and related assets."""

from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .models import PostRecord


def _recipe_urls_for_post(post: PostRecord) -> list[str]:
    """Return unique recipe URLs, supporting both old and new record formats."""

    urls = ([post.recipe_url] if post.recipe_url.strip() else []) + post.recipe_urls
    return list(dict.fromkeys(url.strip() for url in urls if url.strip()))


def _recipe_name_from_url(recipe_url: str) -> str:
    """Derive a readable recipe name from the final segment of its URL."""

    path_segments = [segment for segment in urlsplit(recipe_url).path.split("/") if segment]
    if not path_segments:
        return "Recipe"
    name = unquote(path_segments[-1]).replace("-", " ").replace("_", " ")
    return " ".join(name.split()) or "Recipe"


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
        title_markup = f'<h2 class="card-title" dir="auto">{html.escape(title)}</h2>'

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

        recipe_urls = _recipe_urls_for_post(post)
        primary_recipe_name = (
            post.recipe_names[0].strip()
            if post.recipe_names and post.recipe_names[0].strip()
            else (_recipe_name_from_url(recipe_urls[0]) if recipe_urls else "")
        )
        recipe_markup = "\n".join(
            '<p class="link-row">'
            '<a href="'
            f'{html.escape(recipe_url, quote=True)}'
            f'" target="cookbook-recipe-{html.escape(post.shortcode, quote=True)}{f"-{index}" if index else ""}" rel="noreferrer" dir="auto">'
            f'{html.escape(post.recipe_names[index] if index < len(post.recipe_names) and post.recipe_names[index].strip() else _recipe_name_from_url(recipe_url))}'
            '</a>'
            '</p>'
            for index, recipe_url in enumerate(recipe_urls)
        )

        editor_data = html.escape(
            json.dumps(
                {
                    "id": post.shortcode,
                    "title": title,
                    "sourceUrl": post.url,
                    "recipeUrl": recipe_urls[0] if recipe_urls else "",
                    "recipeName": primary_recipe_name,
                    "imageUrl": post.image_url,
                    "notes": "",
                },
                ensure_ascii=False,
            ),
            quote=True,
        )

        cards.append(
            f"""
      <article class=\"card\" data-recipe-id=\"{html.escape(post.shortcode, quote=True)}\" data-recipe=\"{editor_data}\">
        {title_markup}
        <p class=\"link-row source-link\">
          <a href=\"{html.escape(post.url, quote=True)}\" target=\"_blank\" rel=\"noreferrer\">
            אינסטגרם
          </a>
        </p>
        <div class=\"recipe-links\">{recipe_markup}</div>
        <p class=\"link-row notes-link\"><a href=\"notes.html?id={html.escape(post.shortcode, quote=True)}\">Notes</a></p>
        <div class=\"card-image\">{img_markup}</div>
        <button class=\"edit-recipe\" type=\"button\">Edit recipe</button>
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
    <title>Liora's cookbook</title>
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
      .page-header {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 8px; }}
      .page-header h1 {{ margin: 0; }}
      .link-row {{
        margin: 0 0 10px;
      }}
      .source-link {{ text-align: right; direction: rtl; }}
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
      button {{ border: 0; border-radius: 7px; padding: 9px 13px; background: #8db7ff; color: #101218; font: inherit; font-weight: 600; cursor: pointer; }}
      .edit-recipe {{ margin-top: 4px; background: #2a2f3a; color: #eceef3; }}
      dialog {{ width: min(520px, calc(100% - 32px)); border: 1px solid #3a414f; border-radius: 12px; padding: 0; background: #171a21; color: #eceef3; }}
      dialog::backdrop {{ background: rgba(0, 0, 0, 0.72); }}
      .recipe-form {{ display: grid; gap: 14px; padding: 22px; }}
      .recipe-form h2 {{ margin: 0; }}
      .recipe-form label {{ display: grid; gap: 6px; color: #cbd1dc; }}
      .recipe-form input {{ box-sizing: border-box; width: 100%; border: 1px solid #3a414f; border-radius: 7px; padding: 10px 12px; background: #101218; color: #eceef3; font: inherit; }}
      .recipe-form textarea {{ box-sizing: border-box; width: 100%; min-height: 110px; resize: vertical; border: 1px solid #3a414f; border-radius: 7px; padding: 10px 12px; background: #101218; color: #eceef3; font: inherit; }}
      .form-actions {{ display: flex; justify-content: flex-end; gap: 8px; }}
      .secondary-button {{ background: #2a2f3a; color: #eceef3; }}
      .danger-button {{ margin-right: auto; background: #7d2c32; color: #fff; }}
      .save-status {{ min-height: 1.25em; margin: 0; color: #92d3a2; font-size: .9rem; }}
      img {{
        display: block;
        width: 100%;
        max-height: 640px;
        object-fit: contain;
        border-radius: 10px;
        margin: 0 0 14px;
        background: #101218;
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
      <div class="page-header">
        <h1>Liora's cookbook</h1>
        <button id="add-recipe" type="button">Add recipe</button>
      </div>
      <p class="link-row"><a href="shopping_list.html">Open shopping list</a></p>
      <section class=\"grid\" id=\"recipe-grid\">
{cards_markup}
      </section>
    </main>
    <dialog id="recipe-dialog">
      <form class="recipe-form" id="recipe-form">
        <h2 id="recipe-form-title">Add recipe</h2>
        <input id="recipe-id" type="hidden" />
        <label>Recipe name <input id="recipe-title" type="text" maxlength="160" required /></label>
        <label>Recipe link <input id="recipe-url" type="url" placeholder="https://..." /></label>
        <label>Source link <input id="source-url" type="url" placeholder="https://..." /></label>
        <label>Image link <input id="image-url" type="text" placeholder="https://..." /></label>
        <p class="save-status" id="save-status" aria-live="polite"></p>
        <div class="form-actions">
          <button class="danger-button" id="delete-recipe" type="button">Delete</button>
          <button class="secondary-button" id="cancel-recipe" type="button">Cancel</button>
          <button type="submit">Save</button>
        </div>
      </form>
    </dialog>
    <script>
      (() => {{
        const storageKey = "cookbook-recipe-changes-v1";
        const scrollStorageKey = "cookbook-main-scroll-position";
        const grid = document.getElementById("recipe-grid");
        const dialog = document.getElementById("recipe-dialog");
        const form = document.getElementById("recipe-form");
        const formTitle = document.getElementById("recipe-form-title");
        const idInput = document.getElementById("recipe-id");
        const titleInput = document.getElementById("recipe-title");
        const recipeUrlInput = document.getElementById("recipe-url");
        const sourceUrlInput = document.getElementById("source-url");
        const imageUrlInput = document.getElementById("image-url");
        const deleteButton = document.getElementById("delete-recipe");
        const saveStatus = document.getElementById("save-status");
        const baseIds = new Set([...grid.querySelectorAll("[data-recipe-id]")].map((card) => card.dataset.recipeId));
        let state;
        try {{ state = JSON.parse(localStorage.getItem(storageKey) || '{{"overrides":{{}},"custom":[]}}'); }}
        catch {{ state = {{ overrides: {{}}, custom: [] }}; }}
        if (!state || typeof state !== "object") state = {{ overrides: {{}}, custom: [] }};
        state.overrides ||= {{}};
        state.custom ||= [];

        const save = () => localStorage.setItem(storageKey, JSON.stringify(state));
        const safeLink = (value) => {{
          if (!value) return "";
          try {{ const url = new URL(value, window.location.href); return ["http:", "https:", "file:"].includes(url.protocol) ? url.href : ""; }}
          catch {{ return ""; }}
        }};
        const linkRow = (url, label, className = "", targetName = "_blank") => {{
          if (!url) return null;
          const row = document.createElement("p"); row.className = `link-row ${{className}}`;
          const link = document.createElement("a"); link.href = url; link.target = targetName; link.rel = "noreferrer"; link.dir = "auto"; link.textContent = label;
          row.append(link); return row;
        }};
        const recipeNameFromUrl = (url) => {{
          try {{
            const segment = new URL(url, window.location.href).pathname.split("/").filter(Boolean).pop();
            return segment ? decodeURIComponent(segment).replace(/[-_]+/g, " ").replace(/\\s+/g, " ").trim() : "Recipe";
          }} catch {{ return "Recipe"; }}
        }};
        const updateCard = (card, recipe) => {{
          card.querySelector(".card-title").textContent = recipe.title;
          const source = card.querySelector(".source-link");
          const newSource = linkRow(safeLink(recipe.sourceUrl), "אינסטגרם", "source-link") || document.createElement("p");
          newSource.className ||= "link-row source-link"; newSource.hidden = !recipe.sourceUrl;
          source.replaceWith(newSource);
          const links = card.querySelector(".recipe-links"); links.replaceChildren();
          const recipeLink = linkRow(safeLink(recipe.recipeUrl), recipe.recipeName || recipeNameFromUrl(recipe.recipeUrl), "", `cookbook-recipe-${{recipe.id}}`); if (recipeLink) links.append(recipeLink);
          card.querySelector(".notes-link a").href = `notes.html?id=${{encodeURIComponent(recipe.id)}}`;
          const imageBox = card.querySelector(".card-image"); imageBox.replaceChildren();
          const imageUrl = safeLink(recipe.imageUrl);
          if (imageUrl) {{ const image = document.createElement("img"); image.src = imageUrl; image.alt = recipe.title; image.loading = "lazy"; imageBox.append(image); }}
          card.dataset.recipe = JSON.stringify(recipe);
        }};
        const createCard = (recipe) => {{
          const card = document.createElement("article"); card.className = "card"; card.dataset.recipeId = recipe.id;
          card.innerHTML = '<h2 class="card-title" dir="auto"></h2><p class="link-row source-link"></p><div class="recipe-links"></div><p class="link-row notes-link"><a>Notes</a></p><div class="card-image"></div><button class="edit-recipe" type="button">Edit recipe</button>';
          updateCard(card, recipe); return card;
        }};
        const recipeFromCard = (card) => JSON.parse(card.dataset.recipe);
        const openEditor = (recipe, isCustom) => {{
          form.reset(); idInput.value = recipe.id; titleInput.value = recipe.title || ""; recipeUrlInput.value = recipe.recipeUrl || "";
          sourceUrlInput.value = recipe.sourceUrl || ""; imageUrlInput.value = recipe.imageUrl || "";
          formTitle.textContent = recipe.id ? "Edit recipe" : "Add recipe"; deleteButton.hidden = !isCustom; saveStatus.textContent = ""; dialog.showModal(); titleInput.focus();
        }};
        grid.querySelectorAll("[data-recipe-id]").forEach((card) => {{
          const override = state.overrides[card.dataset.recipeId];
          if (override) {{
            const baseRecipe = recipeFromCard(card);
            updateCard(card, {{ ...baseRecipe, ...override, recipeName: override.recipeName || baseRecipe.recipeName }});
          }}
        }});
        state.custom.forEach((recipe) => grid.append(createCard(recipe)));
        const savedScrollPosition = sessionStorage.getItem(scrollStorageKey);
        if (savedScrollPosition !== null) {{
          sessionStorage.removeItem(scrollStorageKey);
          const restoreScroll = () => window.scrollTo(0, Number(savedScrollPosition) || 0);
          requestAnimationFrame(restoreScroll);
          window.addEventListener("load", restoreScroll, {{ once: true }});
        }}
        document.getElementById("add-recipe").addEventListener("click", () => openEditor({{ id: "", title: "", recipeUrl: "", sourceUrl: "", imageUrl: "", notes: "" }}, true));
        document.getElementById("cancel-recipe").addEventListener("click", () => dialog.close());
        grid.addEventListener("click", (event) => {{
          if (event.target.closest(".notes-link a")) sessionStorage.setItem(scrollStorageKey, String(window.scrollY));
        }});
        grid.addEventListener("click", (event) => {{
          const button = event.target.closest(".edit-recipe"); if (!button) return;
          const card = button.closest("[data-recipe-id]"); openEditor(recipeFromCard(card), !baseIds.has(card.dataset.recipeId));
        }});
        form.addEventListener("submit", (event) => {{
          event.preventDefault();
          const existingId = idInput.value;
          const previous = existingId ? recipeFromCard(grid.querySelector(`[data-recipe-id="${{CSS.escape(existingId)}}"]`)) : {{}};
          const recipe = {{ id: existingId || `custom-${{Date.now()}}-${{Math.random().toString(16).slice(2)}}`, title: titleInput.value.trim(), recipeUrl: safeLink(recipeUrlInput.value.trim()), recipeName: previous.recipeName || "", sourceUrl: safeLink(sourceUrlInput.value.trim()), imageUrl: safeLink(imageUrlInput.value.trim()), notes: previous.notes || "" }};
          if (!recipe.title) return;
          if (baseIds.has(recipe.id)) state.overrides[recipe.id] = recipe;
          else {{ const index = state.custom.findIndex((item) => item.id === recipe.id); if (index >= 0) state.custom[index] = recipe; else state.custom.push(recipe); }}
          save(); const card = grid.querySelector(`[data-recipe-id="${{CSS.escape(recipe.id)}}"]`); if (card) updateCard(card, recipe); else grid.prepend(createCard(recipe));
          saveStatus.textContent = "Saved in this browser."; setTimeout(() => dialog.close(), 350);
        }});
        deleteButton.addEventListener("click", () => {{
          const id = idInput.value; if (!id || baseIds.has(id)) return;
          state.custom = state.custom.filter((recipe) => recipe.id !== id); save(); grid.querySelector(`[data-recipe-id="${{CSS.escape(id)}}"]`)?.remove(); dialog.close();
        }});
      }})();
    </script>
  </body>
</html>
"""


def render_notes_html(posts: list[PostRecord], favicon_href: str) -> str:
    """Render recipe notes on their own page, sharing cookbook local storage."""

    base_recipes = [
        {
            "id": post.shortcode,
            "title": _title_for_post(post, {}),
            "sourceUrl": post.url,
            "recipeUrl": (_recipe_urls_for_post(post) or [""])[0],
            "imageUrl": post.image_url,
            "notes": "",
        }
        for post in posts
    ]
    recipes_json = json.dumps(base_recipes, ensure_ascii=False).replace("</", "<\\/")
    safe_favicon_href = html.escape(favicon_href, quote=True)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Recipe notes</title>
    <link rel="icon" type="image/svg+xml" href="{safe_favicon_href}" />
    <style>
      body {{ margin: 0; background: #0f1115; color: #eceef3; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
      main {{ max-width: 760px; margin: 0 auto; padding: 32px 16px 48px; }}
      a {{ color: #8db7ff; }}
      h1 {{ margin-bottom: 8px; }}
      .intro {{ color: #b5bcc9; margin-bottom: 24px; }}
      .notes-grid {{ display: grid; gap: 16px; }}
      .note-card {{ background: #171a21; border: 1px solid #2a2f3a; border-radius: 12px; padding: 16px; }}
      .note-card h2 {{ margin: 0 0 10px; font-size: 1.1rem; }}
      textarea {{ box-sizing: border-box; width: 100%; min-height: 120px; resize: vertical; border: 1px solid #3a414f; border-radius: 7px; padding: 10px 12px; background: #101218; color: #eceef3; font: inherit; }}
      .status {{ min-height: 1.25em; margin: 7px 0 0; color: #92d3a2; font-size: .9rem; }}
    </style>
  </head>
  <body>
    <main>
      <a href="lizapanelim_posts.html">Back to cookbook</a>
      <h1 id="page-title">Recipe notes</h1>
      <p class="intro" id="intro">This note is saved automatically in this browser.</p>
      <section class="notes-grid" id="notes-grid"></section>
    </main>
    <script>
      (() => {{
        const storageKey = "cookbook-recipe-changes-v1";
        const baseRecipes = {recipes_json};
        let state;
        try {{ state = JSON.parse(localStorage.getItem(storageKey) || '{{"overrides":{{}},"custom":[]}}'); }}
        catch {{ state = {{ overrides: {{}}, custom: [] }}; }}
        state.overrides ||= {{}};
        state.custom ||= [];
        const recipes = baseRecipes.map((recipe) => ({{ ...recipe, ...(state.overrides[recipe.id] || {{}}) }})).concat(state.custom);
        const grid = document.getElementById("notes-grid");
        const recipeId = new URLSearchParams(window.location.search).get("id");
        const recipe = recipes.find((candidate) => candidate.id === recipeId);
        if (!recipe) {{
          document.getElementById("page-title").textContent = "Recipe not found";
          document.getElementById("intro").textContent = "Open notes from a recipe card in the cookbook.";
          return;
        }}
        document.title = `${{recipe.title || "Recipe"}} notes`;
        document.getElementById("page-title").textContent = recipe.title || "Untitled recipe";
        {{
          const card = document.createElement("article"); card.className = "note-card";
          const title = document.createElement("h2"); title.textContent = "Notes";
          const input = document.createElement("textarea"); input.dir = "rtl"; input.maxLength = 2000;
          input.placeholder = "הוסיפו טיפים להכנה, תחליפים או הערות נוספות..."; input.value = recipe.notes || "";
          const status = document.createElement("p"); status.className = "status"; status.setAttribute("aria-live", "polite");
          input.addEventListener("input", () => {{
            recipe.notes = input.value;
            const customIndex = state.custom.findIndex((item) => item.id === recipe.id);
            if (customIndex >= 0) state.custom[customIndex] = {{ ...state.custom[customIndex], notes: recipe.notes }};
            else state.overrides[recipe.id] = {{ ...recipe }};
            localStorage.setItem(storageKey, JSON.stringify(state));
            status.textContent = "Saved."; clearTimeout(input.saveTimer);
            input.saveTimer = setTimeout(() => {{ status.textContent = ""; }}, 1000);
          }});
          card.append(title, input, status); grid.append(card);
        }}
      }})();
    </script>
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
