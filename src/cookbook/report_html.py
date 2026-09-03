"""HTML report rendering and related assets."""

from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .models import PostItem


def _recipe_urls_for_post(post: PostItem) -> list[str]:
    """Return unique recipe URLs, supporting both old and new item formats."""

    urls = ([post.recipe_url] if post.recipe_url.strip() else []) + post.recipe_urls
    return list(dict.fromkeys(url.strip() for url in urls if url.strip()))


def _recipe_name_from_url(recipe_url: str) -> str:
    """Derive a readable recipe name from the final segment of its URL."""

    path_segments = [segment for segment in urlsplit(recipe_url).path.split("/") if segment]
    if not path_segments:
        return "Recipe"
    name = unquote(path_segments[-1]).replace("-", " ").replace("_", " ")
    return " ".join(name.split()) or "Recipe"


def _title_for_post(post: PostItem, titles: dict[str, str]) -> str:
    """Prefer a user-provided title, then use the first caption line."""

    if post.title.strip():
        return post.title.strip()

    sidecar_title = titles.get(post.shortcode, "").strip()
    if sidecar_title:
        return sidecar_title

    caption_lines = [line.strip() for line in post.caption.splitlines() if line.strip()]
    return caption_lines[0] if caption_lines else ""


def render_html(
    posts: list[PostItem],
    username: str,
    favicon_href: str,
    titles: dict[str, str] | None = None,
) -> str:
    """Render fetched posts into a standalone HTML document."""

    titles = titles or {}
    base_recipes: list[dict[str, object]] = []
    for post in posts:
        title = _title_for_post(post, titles)
        recipe_urls = _recipe_urls_for_post(post)
        recipe_names = [
            post.recipe_names[index].strip()
            if index < len(post.recipe_names) and post.recipe_names[index].strip()
            else _recipe_name_from_url(recipe_url)
            for index, recipe_url in enumerate(recipe_urls)
        ]
        base_recipes.append(
            {
                "id": post.shortcode,
                "title": title,
                "sourceUrl": post.url,
                "recipeUrl": recipe_urls[0] if recipe_urls else "",
                "recipeName": recipe_names[0] if recipe_names else "",
                "recipeUrls": recipe_urls,
                "recipeNames": recipe_names,
                "imageUrl": post.image_url,
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
      .page-header h1 {{ margin: 0; text-align: right; direction: rtl; }}
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
      .source-link {{ text-align: right; direction: rtl; }}
      .recipe-links {{ text-align: right; }}
      .notes-link {{ text-align: right; }}
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
      @media (max-width: 480px) {{ .recipe-prerequisite {{ flex-wrap: wrap; white-space: normal; }} .recipe-prerequisite select {{ flex-basis: 100%; }} }}
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
        <button id="add-recipe" type="button">הוסף מתכון</button>
      </div>
      <section class=\"grid\" id=\"recipe-grid\"></section>
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
      (() => {{
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
        const baseIds = new Set(baseRecipes.map((recipe) => recipe.id));
        let state;
        try {{ state = JSON.parse(localStorage.getItem(storageKey) || '{{"overrides":{{}},"custom":[]}}'); }}
        catch {{ state = {{ overrides: {{}}, custom: [] }}; }}
        if (!state || typeof state !== "object") state = {{ overrides: {{}}, custom: [] }};
        state.overrides ||= {{}};
        state.custom ||= [];
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

        const save = () => localStorage.setItem(storageKey, JSON.stringify(state));
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
          card.querySelector(".card-title").textContent = recipe.title;
          const source = card.querySelector(".source-link");
          const newSource = linkRow(safeLink(recipe.sourceUrl), "אינסטגרם", "source-link") || document.createElement("p");
          newSource.className ||= "link-row source-link"; newSource.hidden = !recipe.sourceUrl;
          source.replaceWith(newSource);
          const links = card.querySelector(".recipe-links"); links.replaceChildren();
          const recipeUrls = [...new Set([recipe.recipeUrl, ...(recipe.recipeUrls || [])].map(safeLink).filter(Boolean))];
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
          card.querySelector(".notes-link a").href = `notes.html?id=${{encodeURIComponent(recipe.id)}}`;
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
            ? `#recipe-${{encodeURIComponent(prerequisiteSelect.value)}}`
            : "#";
          const imageBox = card.querySelector(".card-image"); imageBox.replaceChildren();
          const imageUrl = safeLink(recipe.imageUrl);
          if (imageUrl) {{
            const image = document.createElement("img"); image.src = imageUrl; image.alt = recipe.title; image.loading = "lazy";
            const sourceUrl = safeLink(recipe.sourceUrl);
            if (sourceUrl) {{ const imageLink = document.createElement("a"); imageLink.href = sourceUrl; imageLink.target = "_blank"; imageLink.rel = "noreferrer"; imageLink.append(image); imageBox.append(imageLink); }}
            else imageBox.append(image);
          }}
          card.dataset.recipe = JSON.stringify(recipe);
        }};
        const createCard = (recipe) => {{
          const card = document.createElement("article"); card.className = "card"; card.dataset.recipeId = recipe.id; card.id = `recipe-${{encodeURIComponent(recipe.id)}}`;
          card.innerHTML = '<h2 class="card-title" dir="auto"></h2><p class="link-row source-link"></p><div class="recipe-links"></div><div class="recipe-prerequisite"><span>דרוש הכנה של</span><select aria-label="דרוש הכנה של"></select><a class="prerequisite-link">למתכון</a></div><section class="recipe-ingredients"><h3>מצרכים</h3><table class="ingredients-table"><thead><tr><th scope="col">שם</th><th scope="col">זנים מועדפים</th><th scope="col">כמות</th></tr></thead><tbody></tbody></table></section><section class="recipe-instructions"><h3>הוראות הכנה</h3><pre></pre></section><p class="link-row notes-link"><a>הערות</a></p><button class="edit-recipe" type="button">עריכת המתכון</button><div class="card-image"></div>';
          updateCard(card, recipe); return card;
        }};
        const recipeFromCard = (card) => JSON.parse(card.dataset.recipe);
        const openEditor = (recipe, isCustom) => {{
          form.reset(); idInput.value = recipe.id; titleInput.value = recipe.title || ""; recipeUrlInput.value = recipe.recipeUrl || "";
          sourceUrlInput.value = recipe.sourceUrl || ""; imageUrlInput.value = recipe.imageUrl || "";
          ingredientsEditorBody.replaceChildren();
          const ingredients = normalizeIngredients(recipe.ingredients);
          (ingredients.length ? ingredients : [{{}}]).forEach(addIngredientRow);
          instructionsInput.value = recipe.instructions || "";
          formTitle.textContent = recipe.id ? "Edit recipe" : "Add recipe"; deleteButton.hidden = !isCustom; saveStatus.textContent = ""; dialog.showModal(); titleInput.focus();
        }};
        const recipesById = new Map(allRecipes().map((recipe) => [recipe.id, recipe]));
        state.order.forEach((id) => grid.append(createCard(recipesById.get(id))));
        save();
        grid.querySelectorAll("[data-recipe-id]").forEach((card) => updateCard(card, recipeFromCard(card)));
        if (!grid.children.length) grid.innerHTML = "<p>No posts found.</p>";
        const savedScrollPosition = sessionStorage.getItem(scrollStorageKey);
        if (savedScrollPosition !== null) {{
          sessionStorage.removeItem(scrollStorageKey);
          const restoreScroll = () => window.scrollTo(0, Number(savedScrollPosition) || 0);
          requestAnimationFrame(restoreScroll);
          window.addEventListener("load", restoreScroll, {{ once: true }});
        }}
        document.getElementById("add-recipe").addEventListener("click", () => openEditor({{ id: "", title: "", recipeUrl: "", sourceUrl: "", imageUrl: "", ingredients: [], instructions: "", prerequisiteId: "", notes: "" }}, true));
        document.getElementById("add-ingredient").addEventListener("click", () => addIngredientRow());
        document.getElementById("cancel-recipe").addEventListener("click", () => dialog.close());
        grid.addEventListener("click", (event) => {{
          if (event.target.closest(".notes-link a")) sessionStorage.setItem(scrollStorageKey, String(window.scrollY));
        }});
        grid.addEventListener("change", (event) => {{
          const select = event.target.closest(".recipe-prerequisite select"); if (!select) return;
          const card = select.closest("[data-recipe-id]");
          const recipe = {{ ...recipeFromCard(card), prerequisiteId: select.value }};
          if (baseIds.has(recipe.id)) state.overrides[recipe.id] = recipe;
          else {{ const index = state.custom.findIndex((item) => item.id === recipe.id); if (index >= 0) state.custom[index] = recipe; }}
          save(); updateCard(card, recipe);
        }});
        grid.addEventListener("click", (event) => {{
          const button = event.target.closest(".edit-recipe"); if (!button) return;
          const card = button.closest("[data-recipe-id]"); openEditor(recipeFromCard(card), !baseIds.has(card.dataset.recipeId));
        }});
        form.addEventListener("submit", (event) => {{
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
          }};
          if (!recipe.title) return;
          if (baseIds.has(recipe.id)) state.overrides[recipe.id] = recipe;
          else {{ const index = state.custom.findIndex((item) => item.id === recipe.id); if (index >= 0) state.custom[index] = recipe; else state.custom.push(recipe); }}
          if (!state.order.includes(recipe.id)) state.order.push(recipe.id);
          save(); const card = grid.querySelector(`[data-recipe-id="${{CSS.escape(recipe.id)}}"]`); if (card) updateCard(card, recipe); else grid.append(createCard(recipe));
          grid.querySelectorAll("[data-recipe-id]").forEach((recipeCard) => updateCard(recipeCard, recipeFromCard(recipeCard)));
          saveStatus.textContent = "Saved in this browser."; setTimeout(() => dialog.close(), 350);
        }});
        deleteButton.addEventListener("click", () => {{
          const id = idInput.value; if (!id || baseIds.has(id)) return;
          state.custom = state.custom.filter((recipe) => recipe.id !== id); state.order = state.order.filter((recipeId) => recipeId !== id); save(); grid.querySelector(`[data-recipe-id="${{CSS.escape(id)}}"]`)?.remove();
          grid.querySelectorAll("[data-recipe-id]").forEach((card) => updateCard(card, recipeFromCard(card)));
          dialog.close();
        }});
      }})();
    </script>
  </body>
</html>
"""


def render_notes_html(posts: list[PostItem], favicon_href: str) -> str:
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
      (() => {{
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
        let items = JSON.parse(localStorage.getItem(storageKey) || "[]");
        const save = () => {{
          localStorage.setItem(storageKey, JSON.stringify(items));
          if (location.protocol.startsWith("http")) fetch("/api/shopping-list", {{
            method: "PUT",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify(items),
          }}).catch(() => {{ exportStatus.textContent = "השמירה לקובץ נכשלה; הרשימה נשמרה בדפדפן בלבד."; }});
        }};
        const loadPersistedItems = async () => {{
          if (!location.protocol.startsWith("http")) return;
          try {{
            const response = await fetch("/api/shopping-list");
            if (!response.ok) throw new Error("Unable to load shopping list");
            const persistedItems = await response.json();
            if (Array.isArray(persistedItems)) {{
              items = persistedItems;
              localStorage.setItem(storageKey, JSON.stringify(items));
              render();
            }} else if (items.length) {{
              save();
            }}
          }} catch (error) {{
            exportStatus.textContent = "לא ניתן לטעון את הקובץ; מוצגת הרשימה השמורה בדפדפן.";
          }}
        }};
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
          trelloButton.disabled = items.length === 0;
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
        loadPersistedItems();
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
