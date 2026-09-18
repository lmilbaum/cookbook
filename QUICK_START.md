# Quick start

Requires Docker Compose and Python 3.11+ with `uv`.

```sh
uv sync
make up
```

Open http://localhost:8765/. Compose starts PostgreSQL,
applies schema migrations, and serves database-backed cookbook pages.
`make down` stops the services and retains the database volume.

## Import existing data

Back up PostgreSQL and export browser-only edits before switching. See the
[README](README.md) for backup and migration details. Configure `DATABASE_URL`
in `.env` for host commands, matching the Compose database settings.

```sh
uv run cookbook-import-post-store --store lizapanelim_posts_items
# Optional separate legacy titles:
uv run cookbook-import-post-store --store lizapanelim_posts_items --titles lizapanelim_posts_titles.json
uv run cookbook-import-shopping-list --file shopping_list.json
uv run cookbook-import-recipe-state --file recipe-state.json
```

Post imports preserve existing database edits. Shopping-list and recipe-state
imports refuse initialized storage; do not reset it to force an import. Source
files are retained. Refresh open browser tabs after an application upgrade.

## Fetch new posts

In the hosted cookbook, click **ייבוא הפוסט הבא מהסוף** beside Add recipe to
import one unseen post from the feed end. Wait for completion, then click
**Refresh cookbook**. This uses the application's scraper directly, without AI.
The commands below remain available for bulk or manual imports.


Configure `cookbook.toml` and local Instagram credentials in `.env`.

```sh
uv run playwright install chromium
uv run cookbook --config cookbook.toml --no-open
```

Set `use_browser = true` to use Playwright directly. Otherwise the importer tries
the API and falls back to the browser on unauthorized responses. See
[BROWSER_SCRAPER.md](BROWSER_SCRAPER.md) for scraper setup. View new posts through
the hosted cookbook to use shared database edits; opening exported HTML through
`file://` uses browser-only edits.

## Verify changes

```sh
uv run pytest
git diff --check
docker compose exec -T -e PYTHONPATH=/data/src app python /data/scripts/verify_postgres_migration.py
```

The PostgreSQL check uses synthetic data in a disposable schema.
