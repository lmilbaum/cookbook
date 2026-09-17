"""HTML report rendering and related assets."""

from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .models import Recipe


def _recipe_name_from_url(recipe_url: str) -> str:
    """Derive a readable recipe name from the final segment of its URL."""

    path_segments = [segment for segment in urlsplit(recipe_url).path.split("/") if segment]
    if not path_segments:
        return "Recipe"
    name = unquote(path_segments[-1]).replace("-", " ").replace("_", " ")
    return " ".join(name.split()) or "Recipe"


def _title_for_recipe(recipe: Recipe, titles: dict[str, str]) -> str:
    """Prefer a user-provided title, then use the first caption line."""

    if recipe.title.strip():
        return recipe.title.strip()

    sidecar_title = titles.get(recipe.id, "").strip()
    if sidecar_title:
        return sidecar_title

    caption_lines = [line.strip() for line in recipe.caption.splitlines() if line.strip()]
    return caption_lines[0] if caption_lines else ""


_RECIPE_STATE_SCRIPT = r"""
        const persistenceStatus = document.createElement("p");
        persistenceStatus.setAttribute("role", "status");
        persistenceStatus.hidden = true;
        document.querySelector("main").prepend(persistenceStatus);
        const hosted = location.protocol.startsWith("http");
        let revision = 0;
        let blocked = false;
        let pendingSave = Promise.resolve();
        const backupKey = `${storageKey}-backup-${Date.now()}`;
        const persistSnapshot = async (snapshot) => {
          if (blocked) throw new Error("Reload before saving again. Your browser backup is retained.");
          const response = await fetch("/api/recipe-state", {
            method: "PUT", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ state: snapshot, revision }),
          });
          if (!response.ok) {
            blocked = true;
            throw new Error(response.status === 409
              ? "Recipes changed in another tab. Reload before saving. Your browser backup is retained."
              : "Database save failed. Your browser backup is retained. Reload to retry.");
          }
          revision = (await response.json()).revision;
        };
        if (hosted) {
          try {
            const response = await fetch("/api/recipe-state", { cache: "no-store" });
            if (!response.ok) throw new Error();
            const persisted = await response.json();
            revision = persisted.revision;
            if (revision === 0 && (Object.keys(state.overrides).length || state.custom.length)) {
              await persistSnapshot(state);
            } else {
              state = persisted.state;
            }
          } catch {
            persistenceStatus.hidden = false;
            persistenceStatus.textContent = "Unable to load recipes. Reload to retry; browser data is retained.";
            document.querySelectorAll("button, input, textarea, select").forEach((control) => control.disabled = true);
            return;
          }
        }
        const statusVersions = new WeakMap();
        const showSaveStatus = (target, message, temporary = false) => {
          clearTimeout(target.saveTimer);
          target.textContent = message;
          if (temporary) target.saveTimer = setTimeout(() => { target.textContent = ""; }, 2000);
        };
        const save = (target) => {
          const version = (statusVersions.get(target) || 0) + 1;
          statusVersions.set(target, version);
          const report = (message, temporary = false) => {
            if (statusVersions.get(target) === version) showSaveStatus(target, message, temporary);
          };
          const snapshot = JSON.parse(JSON.stringify(state));
          let backupSaved = true;
          try {
            localStorage.setItem(hosted ? backupKey : storageKey, JSON.stringify(snapshot));
          } catch {
            backupSaved = false;
          }
          if (!hosted) {
            report(backupSaved ? "Saved." : "Unable to save in this browser.", backupSaved);
            return Promise.resolve(backupSaved);
          }
          report("Saving…");
          pendingSave = pendingSave.then(async () => {
            try {
              await persistSnapshot(snapshot);
              report("Saved.", true);
              return true;
            } catch (error) {
              blocked = true;
              report(backupSaved ? error.message : "Save failed and browser backup is unavailable. Keep this page open and copy your edits.");
              return false;
            }
          });
          return pendingSave;
        };
"""


_IMPORT_POST_SCRIPT = r"""
      (() => {
        const controls = document.getElementById("import-controls");
        const button = document.getElementById("import-post");
        const status = document.getElementById("import-status");
        const refresh = document.getElementById("import-refresh");
        if (!location.protocol.startsWith("http")) {
          controls.hidden = true;
          return;
        }
        let timer;
        const show = (result) => {
          if (!["idle", "running", "succeeded", "empty", "failed"].includes(result.status)) throw new Error();
          clearTimeout(timer);
          button.disabled = result.status === "running";
          button.setAttribute("aria-busy", String(button.disabled));
          status.textContent = result.message;
          refresh.hidden = result.status !== "succeeded";
          if (button.disabled) timer = setTimeout(check, 2000);
        };
        const check = async () => {
          try {
            const response = await fetch("/api/import-post", { cache: "no-store" });
            if (!response.ok) throw new Error();
            show(await response.json());
          } catch {
            button.disabled = true;
            status.textContent = "Unable to check import status. Reconnecting…";
            timer = setTimeout(check, 3000);
          }
        };
        button.addEventListener("click", async () => {
          button.disabled = true;
          refresh.hidden = true;
          status.textContent = "Starting import…";
          try {
            const response = await fetch("/api/import-post", {
              method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
            });
            if (!response.ok && response.status !== 409) throw new Error();
            show(await response.json());
          } catch {
            // Check whether the server accepted the job; never retry a POST automatically.
            await check();
          }
        });
        check();
      })();
"""


def render_html(
    recipes: list[Recipe],
    username: str,
    favicon_href: str,
    titles: dict[str, str] | None = None,
) -> str:
    """Render fetched recipes into a standalone HTML document."""

    titles = titles or {}
    base_recipes: list[dict[str, object]] = []
    for recipe in recipes:
        title = _title_for_recipe(recipe, titles)
        recipe_url = recipe.recipe_url.strip()
        recipe_urls = [recipe_url] if recipe_url else []
        recipe_name = recipe.recipe_name.strip() or (_recipe_name_from_url(recipe_url) if recipe_url else "")
        base_recipes.append(
            {
                "id": recipe.id,
                "title": title,
                "sourceUrl": recipe.post.url if recipe.post else "",
                "source": recipe.source,
                "recipeUrl": recipe_url,
                "recipeName": recipe_name,
                "recipeUrls": recipe_urls,
                "recipeNames": [recipe_name] if recipe_name else [],
                "imageUrl": recipe.image_url,
                "ingredients": [],
                "instructions": "",
                "prerequisiteId": "",
                "notes": "",
            }
        )

    base_recipes_json = json.dumps(base_recipes, ensure_ascii=False).replace("<", "\\u003c")
    safe_username = html.escape(username)
    safe_favicon_href = html.escape(favicon_href, quote=True)

    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>ספר המתכונים שלי</title>
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
      .page-header {{ display: flex; flex-direction: row-reverse; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 8px; }}
      .header-actions {{ display: flex; flex-wrap: wrap; gap: 8px; }}
      .import-feedback {{ margin: 8px 0 16px; }}
      .import-feedback p {{ margin: 0 0 6px; }}
      button:disabled {{ opacity: .6; cursor: wait; }}
      .page-header h1 {{ margin: 0; text-align: right; direction: rtl; }}
      .back-to-cookbook {{ display: none; margin-bottom: 14px; text-align: right; direction: rtl; }}
      .recipe-view .back-to-cookbook {{ display: block; }}
      .source-filter {{ display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin: 0 0 16px; padding: 10px 12px; border: 1px solid #303644; border-radius: 9px; background: #12151b; direction: rtl; }}
      .source-filter span.meta-label {{ margin: 0; }}
      .source-filter label {{ display: flex; align-items: center; gap: 6px; cursor: pointer; }}
      .recipe-view .source-filter {{ display: none; }}
      .no-filter-results {{ color: #929baa; }}
      .link-row {{
        margin: 0 0 10px;
      }}
      .shopping-list-link {{
        position: fixed;
        right: max(16px, env(safe-area-inset-right));
        bottom: max(16px, env(safe-area-inset-bottom));
        z-index: 10;
        border-radius: 999px;
        padding: 12px 18px;
        background: #8db7ff;
        color: #101218;
        font-weight: 700;
        text-decoration: none;
        box-shadow: 0 6px 22px rgb(0 0 0 / 40%);
      }}
      .shopping-list-link:hover {{ background: #a8c8ff; }}
      .shopping-list-link:focus-visible {{ outline: 3px solid #eceef3; outline-offset: 3px; }}
      .card-header {{ display: grid; justify-items: end; gap: 10px; margin-bottom: 14px; }}
      .card-meta {{ display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 7px 12px; width: fit-content; max-width: 100%; border: 1px solid #303644; border-radius: 9px; padding: 10px 12px; background: #12151b; direction: rtl; text-align: right; }}
      .meta-label {{ color: #929baa; font-size: .82rem; font-weight: 600; line-height: 1.45; }}
      .source-link {{ min-width: 0; text-align: right; direction: rtl; }}
      .recipe-links {{ display: grid; gap: 5px; min-width: 0; text-align: right; }}
      .card-meta .link-row {{ margin: 0; overflow-wrap: anywhere; }}
      .card-meta a {{ text-underline-offset: 3px; }}
      .card-title a {{ color: inherit; text-decoration: none; }}
      .card-title a:hover {{ color: #a8c8ff; }}
      .cookbook-view .card-meta,
      .cookbook-view .recipe-prerequisite,
      .cookbook-view .recipe-ingredients,
      .cookbook-view .recipe-instructions,
      .cookbook-view .recipe-notes,
      .cookbook-view .edit-recipe {{ display: none; }}
      .cookbook-view .card-header {{ margin-bottom: 12px; }}
      .cookbook-view .card-image img {{ margin: 0; }}
      .recipe-view .card-image {{ display: flex; justify-content: flex-end; }}
      .recipe-view .card-image a {{ width: min(220px, 100%); }}
      .recipe-view .card-image img {{ max-height: 220px; margin: 0; }}
      .recipe-view .edit-recipe {{ display: none; }}
      .recipe-view .recipe-form {{ margin-top: 16px; border: 1px solid #303644; border-radius: 10px; background: #12151b; direction: rtl; text-align: right; }}
      .recipe-view .recipe-form h2 {{ font-size: 1.05rem; }}
      .recipe-view .recipe-form .secondary-button {{ display: none; }}
      .recipe-notes {{ margin: 14px 0; padding: 12px; border-radius: 8px; background: #101218; text-align: right; direction: rtl; }}
      .recipe-notes h3 {{ margin: 0 0 8px; font-size: 1rem; }}
      .recipe-notes textarea {{ box-sizing: border-box; width: 100%; min-height: 110px; resize: vertical; border: 1px solid #3a414f; border-radius: 7px; padding: 10px 12px; background: #171a21; color: #eceef3; font: inherit; }}
      .recipe-notes-status {{ min-height: 1.25em; margin: 6px 0 0; color: #92d3a2; font-size: .85rem; }}
      .recipe-instructions {{ margin: 14px 0; padding: 12px; border-radius: 8px; background: #101218; text-align: right; direction: rtl; }}
      .recipe-instructions h3 {{ margin: 0 0 8px; font-size: 1rem; }}
      .recipe-instructions pre {{ margin: 0; }}
      .recipe-ingredients {{ margin: 14px 0; padding: 12px; border-radius: 8px; background: #101218; text-align: right; direction: rtl; }}
      .recipe-ingredients h3 {{ margin: 0 0 8px; font-size: 1rem; }}
      .ingredients-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
      .ingredients-table th, .ingredients-table td {{ padding: 8px 10px; border: 1px solid #3a414f; text-align: right; overflow-wrap: anywhere; }}
      .ingredients-table th {{ background: #242936; color: #eceef3; }}
      .ingredients-table td {{ color: #cbd1dc; }}
      .recipe-prerequisite {{ display: flex; align-items: center; gap: 10px; margin: 12px 0; color: #cbd1dc; text-align: right; direction: rtl; white-space: nowrap; }}
      .recipe-prerequisite select {{ width: min(240px, 100%); min-width: 0; flex: 0 1 240px; border: 1px solid #aeb6c4; border-radius: 7px; padding: 9px 11px; background: #f3f5f8; color: #20242c; font: inherit; }}
      .recipe-prerequisite select:focus {{ outline: 3px solid rgb(141 183 255 / 35%); border-color: #8db7ff; }}
      .prerequisite-link {{ flex: none; color: #8db7ff; }}
      @media (max-width: 480px) {{ .card-meta {{ width: auto; grid-template-columns: 1fr; gap: 4px; }} .meta-label:not(:first-child) {{ margin-top: 5px; }} .recipe-prerequisite {{ flex-wrap: wrap; white-space: normal; }} .recipe-prerequisite select {{ flex-basis: 100%; }} }}
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
        margin: 0;
        font-size: 1.2rem;
        line-height: 1.25;
        text-align: right;
      }}
      button {{ border: 0; border-radius: 7px; padding: 9px 13px; background: #8db7ff; color: #101218; font: inherit; font-weight: 600; cursor: pointer; }}
      .edit-recipe {{ display: block; margin: 0 0 10px auto; padding: 0; background: transparent; color: #8db7ff; font-weight: 400; text-decoration: underline; }}
      .edit-recipe:hover {{ color: #a8c8ff; }}
      .edit-recipe:focus-visible {{ outline: 2px solid #8db7ff; outline-offset: 3px; }}
      dialog {{ width: min(520px, calc(100% - 32px)); border: 1px solid #3a414f; border-radius: 12px; padding: 0; background: #171a21; color: #eceef3; }}
      dialog::backdrop {{ background: rgba(0, 0, 0, 0.72); }}
      .recipe-form {{ display: grid; gap: 14px; padding: 22px; }}
      .recipe-form h2 {{ margin: 0; }}
      .recipe-form label {{ display: grid; gap: 6px; color: #cbd1dc; }}
      .recipe-form input {{ box-sizing: border-box; width: 100%; border: 1px solid #3a414f; border-radius: 7px; padding: 10px 12px; background: #101218; color: #eceef3; font: inherit; }}
      .recipe-form select {{ box-sizing: border-box; width: 100%; border: 1px solid #3a414f; border-radius: 7px; padding: 10px 12px; background: #101218; color: #eceef3; font: inherit; }}
      .recipe-form textarea {{ box-sizing: border-box; width: 100%; min-height: 110px; resize: vertical; border: 1px solid #3a414f; border-radius: 7px; padding: 10px 12px; background: #101218; color: #eceef3; font: inherit; }}
      .ingredients-editor {{ display: grid; gap: 8px; }}
      .ingredients-editor > span {{ color: #cbd1dc; }}
      .ingredients-editor-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; direction: rtl; }}
      .ingredients-editor-table th, .ingredients-editor-table td {{ padding: 5px; border: 1px solid #3a414f; text-align: right; }}
      .ingredients-editor-table th {{ color: #cbd1dc; font-weight: 600; }}
      .ingredients-editor-table th:last-child, .ingredients-editor-table td:last-child {{ width: 42px; }}
      .ingredients-editor-table input {{ min-width: 0; padding: 8px; }}
      .remove-ingredient {{ padding: 7px 9px; background: #7d2c32; color: #fff; }}
      .add-ingredient {{ justify-self: start; background: #2a2f3a; color: #eceef3; }}
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
    <a class="shopping-list-link" href="shopping_list.html" dir="rtl" aria-label="פתיחת רשימת הקניות">רשימת הקניות</a>
    <main>
      <div class="page-header">
        <h1>ספר המתכונים שלי</h1>
        <div class="header-actions">
          <button id="add-recipe" type="button">הוסף מתכון</button>
          <div id="import-controls">
            <button id="import-post" type="button" disabled aria-label="Import next post from the end">ייבוא הפוסט הבא מהסוף</button>
          </div>
        </div>
      </div>
      <div class="import-feedback">
        <p id="import-status" role="status" aria-live="polite"></p>
        <a id="import-refresh" href="lizapanelim_posts.html" hidden>Refresh cookbook</a>
      </div>
      <a class="back-to-cookbook" href="lizapanelim_posts.html">חזרה לכל המתכונים</a>
      <div class="source-filter" id="source-filter" role="group" aria-label="סינון לפי מקור">
        <span class="meta-label">מקור</span>
        <label><input type="checkbox" id="filter-lizapanelim" checked /> ליזה פאנלים</label>
        <label><input type="checkbox" id="filter-other" checked /> אחר</label>
      </div>
      <section class=\"grid\" id=\"recipe-grid\"></section>
      <p class="no-filter-results" id="no-filter-results" hidden>אין מתכונים התואמים לסינון.</p>
    </main>
    <dialog id="recipe-dialog">
      <form class="recipe-form" id="recipe-form">
        <h2 id="recipe-form-title">Add recipe</h2>
        <input id="recipe-id" type="hidden" />
        <label>Recipe name <input id="recipe-title" type="text" maxlength="160" required /></label>
        <label>Recipe link <input id="recipe-url" type="url" placeholder="https://..." /></label>
        <label>Source link <input id="source-url" type="url" placeholder="https://..." /></label>
        <label>Image link <input id="image-url" type="text" placeholder="https://..." /></label>
        <div class="ingredients-editor">
          <span>מצרכים</span>
          <table class="ingredients-editor-table">
            <thead><tr><th scope="col">שם</th><th scope="col">זנים מועדפים</th><th scope="col">כמות</th><th scope="col"><span class="visually-hidden">פעולות</span></th></tr></thead>
            <tbody id="ingredients-editor-body"></tbody>
          </table>
          <button class="add-ingredient" id="add-ingredient" type="button">הוספת מצרך</button>
        </div>
        <label>הוראות הכנה <textarea id="recipe-instructions" maxlength="10000" dir="rtl" placeholder="הקלידו כאן את הוראות ההכנה..."></textarea></label>
        <p class="save-status" id="save-status" aria-live="polite"></p>
        <div class="form-actions">
          <button class="danger-button" id="delete-recipe" type="button">Delete</button>
          <button class="secondary-button" id="cancel-recipe" type="button">Cancel</button>
          <button type="submit">Save</button>
        </div>
      </form>
    </dialog>
    <script>
      (async () => {{
        const storageKey = "cookbook-recipe-changes-v1";
        const scrollStorageKey = "cookbook-main-scroll-position";
        const baseRecipes = {base_recipes_json};
        const grid = document.getElementById("recipe-grid");
        const dialog = document.getElementById("recipe-dialog");
        const form = document.getElementById("recipe-form");
        const formTitle = document.getElementById("recipe-form-title");
        const idInput = document.getElementById("recipe-id");
        const titleInput = document.getElementById("recipe-title");
        const recipeUrlInput = document.getElementById("recipe-url");
        const sourceUrlInput = document.getElementById("source-url");
        const imageUrlInput = document.getElementById("image-url");
        const ingredientsEditorBody = document.getElementById("ingredients-editor-body");
        const instructionsInput = document.getElementById("recipe-instructions");
        const deleteButton = document.getElementById("delete-recipe");
        const saveStatus = document.getElementById("save-status");
        const selectedRecipeId = new URLSearchParams(window.location.search).get("recipe");
        document.body.classList.add(selectedRecipeId ? "recipe-view" : "cookbook-view");
        const baseIds = new Set(baseRecipes.map((recipe) => recipe.id));
        let state;
        try {{ state = JSON.parse(localStorage.getItem(storageKey) || '{{"overrides":{{}},"custom":[]}}'); }}
        catch {{ state = {{ overrides: {{}}, custom: [] }}; }}
        if (!state || typeof state !== "object") state = {{ overrides: {{}}, custom: [] }};
        state.overrides ||= {{}};
        state.custom ||= [];
        {_RECIPE_STATE_SCRIPT}
        const allRecipes = () => baseRecipes
          .map((recipe) => ({{ ...recipe, ...(state.overrides[recipe.id] || {{}}), recipeName: state.overrides[recipe.id]?.recipeName || recipe.recipeName }}))
          .concat(state.custom);
        const availableIds = new Set(allRecipes().map((recipe) => recipe.id));
        if (!Array.isArray(state.order)) {{
          const baseOrder = baseRecipes.map((recipe) => recipe.id);
          const newestBaseId = baseOrder.pop();
          state.order = [...baseOrder, ...state.custom.map((recipe) => recipe.id)];
          if (newestBaseId) state.order.push(newestBaseId);
        }}
        state.order = state.order.filter((id) => availableIds.has(id));
        allRecipes().forEach((recipe) => {{ if (!state.order.includes(recipe.id)) state.order.push(recipe.id); }});

        // Source data owns the order of imported recipes. Preserve browser-only
        // recipes in their existing slots when the source order changes.
        const sourceOrder = baseRecipes.map((recipe) => recipe.id);
        let sourceIndex = 0;
        state.order = state.order.map((id) => baseIds.has(id) ? sourceOrder[sourceIndex++] : id);

        const safeLink = (value) => {{
          if (!value) return "";
          try {{
            const url = new URL(value, window.location.href);
            if (url.protocol === "file:" && window.location.protocol.startsWith("http")) {{
              const localAssetRoot = ["/lizapanelim_posts_assets/", "/recipes/"]
                .find((root) => url.pathname.includes(root));
              return localAssetRoot
                ? `${{window.location.origin}}${{url.pathname.slice(url.pathname.lastIndexOf(localAssetRoot))}}`
                : "";
            }}
            return ["http:", "https:", "file:"].includes(url.protocol) ? url.href : "";
          }}
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
        const normalizeIngredients = (value) => {{
          if (Array.isArray(value)) return value.map((item) => ({{
            name: String(item?.name || "").trim(),
            varieties: String(item?.varieties || "").trim(),
            amount: String(item?.amount || "").trim(),
          }})).filter((item) => item.name || item.varieties || item.amount);
          return String(value || "").split(/\\r?\\n/).map((line) => {{
            const [name = "", varieties = "", ...amountParts] = line.split("|").map((part) => part.trim());
            return {{ name, varieties, amount: amountParts.join(" | ") }};
          }}).filter((item) => item.name || item.varieties || item.amount);
        }};
        const addIngredientRow = (ingredient = {{}}) => {{
          const row = document.createElement("tr");
          ["name", "varieties", "amount"].forEach((field) => {{
            const cell = document.createElement("td");
            const input = document.createElement("input"); input.type = "text"; input.maxLength = 120; input.dataset.field = field; input.value = ingredient[field] || "";
            cell.append(input); row.append(cell);
          }});
          const actionCell = document.createElement("td");
          const remove = document.createElement("button"); remove.type = "button"; remove.className = "remove-ingredient"; remove.textContent = "−"; remove.setAttribute("aria-label", "מחיקת מצרך");
          remove.addEventListener("click", () => {{ row.remove(); if (!ingredientsEditorBody.rows.length) addIngredientRow(); }});
          actionCell.append(remove); row.append(actionCell); ingredientsEditorBody.append(row);
        }};
        const updateCard = (card, recipe) => {{
          card.querySelector(".recipe-detail-link").textContent = recipe.title;
          const detailUrl = `lizapanelim_posts.html?recipe=${{encodeURIComponent(recipe.id)}}`;
          card.querySelector(".recipe-detail-link").href = detailUrl;
          const source = card.querySelector(".source-link");
          const newSource = linkRow(safeLink(recipe.sourceUrl), "אינסטגרם", "source-link") || document.createElement("p");
          newSource.className ||= "link-row source-link"; newSource.hidden = !recipe.sourceUrl;
          source.replaceWith(newSource);
          newSource.previousElementSibling.hidden = newSource.hidden;
          const links = card.querySelector(".recipe-links"); links.replaceChildren();
          const recipeUrls = [...new Set([recipe.recipeUrl, ...(recipe.recipeUrls || [])].map(safeLink).filter(Boolean))];
          links.previousElementSibling.hidden = !recipeUrls.length;
          recipeUrls.forEach((url, index) => {{
            const nameIndex = (recipe.recipeUrls || []).indexOf(url);
            const label = index === 0 && !baseIds.has(recipe.id)
              ? recipe.title
              : index === 0 && recipe.recipeName
                ? recipe.recipeName
                : (recipe.recipeNames || [])[nameIndex] || recipeNameFromUrl(url);
            const target = `cookbook-recipe-${{recipe.id}}${{index ? `-${{index}}` : ""}}`;
            const recipeLink = linkRow(url, label, "", target); if (recipeLink) links.append(recipeLink);
          }});
          card.querySelector(".card-meta").hidden = newSource.hidden && !recipeUrls.length;
          card.querySelector(".recipe-notes textarea").value = recipe.notes || "";
          const ingredientsBox = card.querySelector(".recipe-ingredients");
          const ingredients = normalizeIngredients(recipe.ingredients);
          ingredientsBox.hidden = false;
          const ingredientsBody = ingredientsBox.querySelector("tbody");
          const displayedIngredients = ingredients.length
            ? ingredients
            : [{{ name: "", varieties: "", amount: "" }}];
          ingredientsBody.replaceChildren(...displayedIngredients.map((ingredient) => {{
            const row = document.createElement("tr");
            [ingredient.name, ingredient.varieties, ingredient.amount].forEach((value) => {{
              const cell = document.createElement("td"); cell.textContent = value; row.append(cell);
            }});
            return row;
          }}));
          const instructionsBox = card.querySelector(".recipe-instructions");
          const instructions = (recipe.instructions || "").trim();
          instructionsBox.hidden = !instructions;
          instructionsBox.querySelector("pre").textContent = instructions;
          const prerequisiteSelect = card.querySelector(".recipe-prerequisite select");
          prerequisiteSelect.replaceChildren(new Option("לא נדרש מתכון נוסף", ""));
          grid.querySelectorAll("[data-recipe-id]").forEach((candidateCard) => {{
            const candidate = recipeFromCard(candidateCard);
            if (candidate.id !== recipe.id) prerequisiteSelect.add(new Option(candidate.title, candidate.id));
          }});
          prerequisiteSelect.value = prerequisiteSelect.querySelector(`option[value="${{CSS.escape(recipe.prerequisiteId || "")}}"]`)
            ? recipe.prerequisiteId || ""
            : "";
          const prerequisiteLink = card.querySelector(".prerequisite-link");
          prerequisiteLink.hidden = !prerequisiteSelect.value;
          prerequisiteLink.href = prerequisiteSelect.value
            ? `lizapanelim_posts.html?recipe=${{encodeURIComponent(prerequisiteSelect.value)}}`
            : "#";
          const imageBox = card.querySelector(".card-image"); imageBox.replaceChildren();
          const imageUrl = safeLink(recipe.imageUrl);
          if (imageUrl) {{
            const image = document.createElement("img"); image.src = imageUrl; image.alt = recipe.title; image.loading = "lazy";
            const imageLink = document.createElement("a"); imageLink.href = detailUrl; imageLink.setAttribute("aria-label", `פרטי המתכון: ${{recipe.title}}`); imageLink.append(image); imageBox.append(imageLink);
          }}
          card.dataset.recipe = JSON.stringify(recipe);
        }};
        const createCard = (recipe) => {{
          const card = document.createElement("article"); card.className = "card"; card.dataset.recipeId = recipe.id; card.id = `recipe-${{encodeURIComponent(recipe.id)}}`;
          card.innerHTML = '<header class="card-header"><h2 class="card-title" dir="auto"><a class="recipe-detail-link"></a></h2><div class="card-meta" aria-label="קישורים למתכון"><span class="meta-label">מקור</span><p class="link-row source-link"></p><span class="meta-label">מתכונים</span><div class="recipe-links"></div></div></header><div class="recipe-prerequisite"><span>דרוש הכנה של</span><select aria-label="דרוש הכנה של"></select><a class="prerequisite-link">למתכון</a><span class="prerequisite-status" aria-live="polite"></span></div><section class="recipe-ingredients"><h3>מצרכים</h3><table class="ingredients-table"><thead><tr><th scope="col">שם</th><th scope="col">זנים מועדפים</th><th scope="col">כמות</th></tr></thead><tbody></tbody></table></section><section class="recipe-instructions"><h3>הוראות הכנה</h3><pre></pre></section><section class="recipe-notes"><h3>הערות</h3><textarea aria-label="הערות למתכון"></textarea><p class="recipe-notes-status" aria-live="polite"></p></section><button class="edit-recipe" type="button">עריכת המתכון</button><div class="card-image"></div>';
          updateCard(card, recipe); return card;
        }};
        const recipeFromCard = (card) => JSON.parse(card.dataset.recipe);
        const openEditor = (recipe, isCustom, inline = false) => {{
          form.reset(); idInput.value = recipe.id; titleInput.value = recipe.title || ""; recipeUrlInput.value = recipe.recipeUrl || "";
          sourceUrlInput.value = recipe.sourceUrl || ""; imageUrlInput.value = recipe.imageUrl || "";
          ingredientsEditorBody.replaceChildren();
          const ingredients = normalizeIngredients(recipe.ingredients);
          (ingredients.length ? ingredients : [{{}}]).forEach(addIngredientRow);
          instructionsInput.value = recipe.instructions || "";
          formTitle.textContent = recipe.id ? "עריכת המתכון" : "הוספת מתכון"; deleteButton.hidden = !isCustom; saveStatus.textContent = "";
          if (!inline) {{ dialog.showModal(); titleInput.focus(); }}
        }};
        const sourceFilter = document.getElementById("source-filter");
        const filterLizapanelim = document.getElementById("filter-lizapanelim");
        const filterOther = document.getElementById("filter-other");
        const noFilterResults = document.getElementById("no-filter-results");
        const applySourceFilter = () => {{
          if (selectedRecipeId) return;
          const showLiza = filterLizapanelim.checked;
          const showOther = filterOther.checked;
          let anyVisible = false;
          grid.querySelectorAll("[data-recipe-id]").forEach((card) => {{
            const visible = recipeFromCard(card).source === "lizapanelim" ? showLiza : showOther;
            card.hidden = !visible;
            if (visible) anyVisible = true;
          }});
          noFilterResults.hidden = anyVisible || !grid.children.length;
        }};
        sourceFilter.addEventListener("change", applySourceFilter);
        const recipesById = new Map(allRecipes().map((recipe) => [recipe.id, recipe]));
        state.order.forEach((id) => grid.append(createCard(recipesById.get(id))));
        grid.querySelectorAll("[data-recipe-id]").forEach((card) => updateCard(card, recipeFromCard(card)));
        applySourceFilter();
        if (selectedRecipeId) {{
          grid.querySelectorAll("[data-recipe-id]").forEach((card) => {{ card.hidden = card.dataset.recipeId !== selectedRecipeId; }});
          document.getElementById("add-recipe").hidden = true;
          const selectedCard = grid.querySelector(`[data-recipe-id="${{CSS.escape(selectedRecipeId)}}"]`);
          if (selectedCard) {{
            selectedCard.append(form);
            openEditor(recipeFromCard(selectedCard), !baseIds.has(selectedRecipeId), true);
          }}
        }}
        if (!grid.children.length) grid.innerHTML = "<p>No posts found.</p>";
        const savedScrollPosition = sessionStorage.getItem(scrollStorageKey);
        if (savedScrollPosition !== null) {{
          sessionStorage.removeItem(scrollStorageKey);
          const restoreScroll = () => window.scrollTo(0, Number(savedScrollPosition) || 0);
          requestAnimationFrame(restoreScroll);
          window.addEventListener("load", restoreScroll, {{ once: true }});
        }}
        document.getElementById("add-recipe").addEventListener("click", () => openEditor({{ id: "", title: "", recipeUrl: "", sourceUrl: "", imageUrl: "", ingredients: [], instructions: "", prerequisiteId: "", notes: "", source: "other" }}, true));
        document.getElementById("add-ingredient").addEventListener("click", () => addIngredientRow());
        document.getElementById("cancel-recipe").addEventListener("click", () => dialog.close());
        grid.addEventListener("input", (event) => {{
          const notes = event.target.closest(".recipe-notes textarea"); if (!notes) return;
          const card = notes.closest("[data-recipe-id]");
          const recipe = {{ ...recipeFromCard(card), notes: notes.value }};
          card.dataset.recipe = JSON.stringify(recipe);
          if (baseIds.has(recipe.id)) state.overrides[recipe.id] = recipe;
          else {{ const index = state.custom.findIndex((item) => item.id === recipe.id); if (index >= 0) state.custom[index] = recipe; }}
          save(card.querySelector(".recipe-notes-status"));
        }});
        grid.addEventListener("change", (event) => {{
          const select = event.target.closest(".recipe-prerequisite select"); if (!select) return;
          const card = select.closest("[data-recipe-id]");
          const recipe = {{ ...recipeFromCard(card), prerequisiteId: select.value }};
          if (baseIds.has(recipe.id)) state.overrides[recipe.id] = recipe;
          else {{ const index = state.custom.findIndex((item) => item.id === recipe.id); if (index >= 0) state.custom[index] = recipe; }}
          save(card.querySelector(".prerequisite-status")); updateCard(card, recipe);
        }});
        grid.addEventListener("click", (event) => {{
          const button = event.target.closest(".edit-recipe"); if (!button) return;
          const card = button.closest("[data-recipe-id]"); openEditor(recipeFromCard(card), !baseIds.has(card.dataset.recipeId));
        }});
        form.addEventListener("submit", async (event) => {{
          event.preventDefault();
          const existingId = idInput.value;
          const previous = existingId ? recipeFromCard(grid.querySelector(`[data-recipe-id="${{CSS.escape(existingId)}}"]`)) : {{}};
          const title = titleInput.value.trim();
          const recipeUrl = safeLink(recipeUrlInput.value.trim());
          const extraRecipeLinks = (previous.recipeUrls || [])
            .map((url, index) => ({{ url, name: (previous.recipeNames || [])[index] || recipeNameFromUrl(url) }}))
            .filter((link) => link.url !== previous.recipeUrl && link.url !== recipeUrl);
          const isCustomRecipe = !existingId || !baseIds.has(existingId);
          const recipeName = isCustomRecipe
            ? title
            : recipeUrl === previous.recipeUrl ? previous.recipeName || "" : recipeNameFromUrl(recipeUrl);
          const recipe = {{
            ...previous,
            id: existingId || `custom-${{Date.now()}}-${{Math.random().toString(16).slice(2)}}`,
            title,
            recipeUrl,
            recipeName,
            recipeUrls: [recipeUrl, ...extraRecipeLinks.map((link) => link.url)].filter(Boolean),
            recipeNames: [recipeName, ...extraRecipeLinks.map((link) => link.name)].filter(Boolean),
            sourceUrl: safeLink(sourceUrlInput.value.trim()),
            imageUrl: safeLink(imageUrlInput.value.trim()),
            ingredients: [...ingredientsEditorBody.rows].map((row) => Object.fromEntries(
              [...row.querySelectorAll("input[data-field]")].map((input) => [input.dataset.field, input.value.trim()])
            )).filter((item) => item.name || item.varieties || item.amount),
            instructions: instructionsInput.value.trim(),
            prerequisiteId: previous.prerequisiteId || "",
            notes: previous.notes || "",
            source: previous.source || "other",
          }};
          if (!recipe.title) return;
          if (baseIds.has(recipe.id)) state.overrides[recipe.id] = recipe;
          else {{ const index = state.custom.findIndex((item) => item.id === recipe.id); if (index >= 0) state.custom[index] = recipe; else state.custom.push(recipe); }}
          if (!state.order.includes(recipe.id)) state.order.push(recipe.id);
          const saved = save(saveStatus); const card = grid.querySelector(`[data-recipe-id="${{CSS.escape(recipe.id)}}"]`); if (card) updateCard(card, recipe); else grid.append(createCard(recipe));
          grid.querySelectorAll("[data-recipe-id]").forEach((recipeCard) => updateCard(recipeCard, recipeFromCard(recipeCard)));
          applySourceFilter();
          if (!await saved) return;
          if (!selectedRecipeId) setTimeout(() => dialog.close(), 350);
        }});
        deleteButton.addEventListener("click", async () => {{
          const id = idInput.value; if (!id || baseIds.has(id)) return;
          state.custom = state.custom.filter((recipe) => recipe.id !== id); state.order = state.order.filter((recipeId) => recipeId !== id); if (!await save(saveStatus)) return; grid.querySelector(`[data-recipe-id="${{CSS.escape(id)}}"]`)?.remove();
          grid.querySelectorAll("[data-recipe-id]").forEach((card) => updateCard(card, recipeFromCard(card)));
          applySourceFilter();
          if (selectedRecipeId) window.location.href = "lizapanelim_posts.html";
          else dialog.close();
        }});
      }})();
    </script>
    <script>{_IMPORT_POST_SCRIPT}</script>
  </body>
</html>
"""


def render_notes_html(recipes: list[Recipe], favicon_href: str) -> str:
    """Render recipe notes on their own page, sharing cookbook database state."""

    base_recipes = [
        {
            "id": recipe.id,
            "title": _title_for_recipe(recipe, {}),
            "sourceUrl": recipe.post.url if recipe.post else "",
            "recipeUrl": recipe.recipe_url,
            "imageUrl": recipe.image_url,
            "notes": "",
        }
        for recipe in recipes
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
      <p class="intro" id="intro">Notes are saved automatically.</p>
      <section class="notes-grid" id="notes-grid"></section>
    </main>
    <script>
      (async () => {{
        const storageKey = "cookbook-recipe-changes-v1";
        const baseRecipes = {recipes_json};
        let state;
        try {{ state = JSON.parse(localStorage.getItem(storageKey) || '{{"overrides":{{}},"custom":[]}}'); }}
        catch {{ state = {{ overrides: {{}}, custom: [] }}; }}
        if (!state || typeof state !== "object") state = {{ overrides: {{}}, custom: [] }};
        state.overrides ||= {{}};
        state.custom ||= [];
        {_RECIPE_STATE_SCRIPT}
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
            save(status);
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
      .shopping-form button, .clear-purchased, .export-button {{ border: 0; border-radius: 6px; padding: 10px 14px; background: #24211d; color: #fffaf2; font: inherit; cursor: pointer; }}
      .shopping-items {{ display: grid; gap: 6px; margin-bottom: 14px; }}
      .shopping-item {{ display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #dfd4c5; }}
      .shopping-item label {{ flex: 1; overflow-wrap: anywhere; }}
      .shopping-item.done label {{ color: #83796d; text-decoration: line-through; }}
      .remove-item {{ border: 0; background: transparent; color: #9a3d35; cursor: pointer; }}
      .empty-shopping-list {{ color: #756b60; }}
      .list-footer {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
      .export-actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }}
      .export-button:disabled {{ cursor: not-allowed; opacity: 0.5; }}
      .export-status {{ min-height: 1.4em; margin: 8px 0 0; color: #5f564c; direction: rtl; text-align: right; }}
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
        <div class="export-actions" aria-label="Export shopping list">
          <button class="export-button" id="send-to-trello" type="button" dir="rtl"><span>ייצוא ל־</span><bdi>Trello</bdi></button>
        </div>
        <p class="export-status" id="export-status" role="status" aria-live="polite"></p>
      </section>
    </main>
    <script>
      (async () => {{
        const storageKey = "cookbook-shopping-list";
        const form = document.getElementById("shopping-form");
        const input = document.getElementById("shopping-item-input");
        const itemsElement = document.getElementById("shopping-items");
        const emptyElement = document.getElementById("empty-shopping-list");
        const countElement = document.getElementById("shopping-count");
        const clearButton = document.getElementById("clear-purchased");
        const trelloButton = document.getElementById("send-to-trello");
        const exportStatus = document.getElementById("export-status");
        const setBidiStatus = (prefix, englishText = "", suffix = "") => {{
          exportStatus.replaceChildren(prefix);
          if (englishText) {{
            const isolatedText = document.createElement("bdi");
            isolatedText.textContent = englishText;
            exportStatus.append(isolatedText);
          }}
          if (suffix) exportStatus.append(suffix);
        }};
        const hosted = location.protocol.startsWith("http");
        const backupKey = `${{storageKey}}-backup-${{Date.now()}}`;
        let items = [];
        try {{ items = JSON.parse(localStorage.getItem(storageKey) || "[]"); }} catch {{}}
        if (!Array.isArray(items)) items = [];
        let revision = 0;
        let blocked = false;
        let pendingSave = Promise.resolve();
        const save = () => {{
          const snapshot = JSON.parse(JSON.stringify(items));
          let backupSaved = true;
          try {{ localStorage.setItem(hosted ? backupKey : storageKey, JSON.stringify(snapshot)); }}
          catch {{ backupSaved = false; }}
          if (!hosted) {{
            exportStatus.textContent = backupSaved ? "Saved." : "Browser save failed. Keep this page open and copy your list.";
            return;
          }}
          exportStatus.textContent = "Saving…";
          pendingSave = pendingSave.then(async () => {{
            try {{
              if (blocked) throw new Error("Reload before saving again; your browser backup is retained.");
              const response = await fetch("/api/shopping-list", {{
                method: "PUT", headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({{ items: snapshot, revision }}),
              }});
              if (!response.ok) throw new Error(response.status === 409
                ? "Shopping list changed in another tab. Reload before saving; your browser backup is retained."
                : "Database save failed. Reload to retry; your browser backup is retained.");
              revision = (await response.json()).revision;
              exportStatus.textContent = "Saved.";
            }} catch (error) {{
              blocked = true;
              exportStatus.textContent = backupSaved ? error.message
                : "Save failed and browser backup is unavailable. Keep this page open and copy your list.";
            }}
          }});
        }};
        if (hosted) {{
          document.querySelectorAll("button, input").forEach((control) => control.disabled = true);
          try {{
            const response = await fetch("/api/shopping-list", {{ cache: "no-store" }});
            if (!response.ok) throw new Error();
            const persisted = await response.json();
            if (!Array.isArray(persisted.items) || !Number.isInteger(persisted.revision)) throw new Error();
            items = persisted.items;
            revision = persisted.revision;
            document.querySelectorAll("button, input").forEach((control) => control.disabled = false);
          }} catch {{
            exportStatus.textContent = "Unable to load shopping list. Reload to retry; browser data is retained.";
            document.querySelectorAll("button, input").forEach((control) => control.disabled = true);
            return;
          }}
        }}
        const render = () => {{
          itemsElement.replaceChildren();
          [...items].sort((a, b) => a.name.localeCompare(b.name, "he")).forEach((item) => {{
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
          trelloButton.disabled = items.length === 0;
        }};
        form.addEventListener("submit", async (event) => {{
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
        trelloButton.addEventListener("click", async () => {{
          trelloButton.disabled = true;
          setBidiStatus("מייצא את רשימת הקניות ל־", "Trello", "…");
          try {{
            const response = await fetch("/api/trello/cards", {{
              method: "POST",
              headers: {{ "Content-Type": "application/json" }},
              body: JSON.stringify(items),
            }});
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Trello export failed");
            const statusText = result.action === "updated"
              ? "הכרטיס הקיים עודכן בבורד "
              : "כרטיס חדש נוצר בבורד ";
            setBidiStatus(statusText, "My To Do List", ". ");
            const cardLink = document.createElement("a");
            cardLink.href = result.url;
            cardLink.target = "_blank";
            cardLink.rel = "noopener noreferrer";
            cardLink.textContent = "פתיחת הכרטיס";
            exportStatus.append(cardLink);
          }} catch (error) {{
            setBidiStatus("לא ניתן היה לייצא את הרשימה ל־", "Trello", ".");
          }} finally {{
            trelloButton.disabled = items.length === 0;
          }}
        }});
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
