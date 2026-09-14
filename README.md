# Cookbook

Python tools for importing recipes and serving a personal cookbook.
See [QUICK_START.md](QUICK_START.md) for scraper instructions.

## Import the next post from the application

Use **ייבוא הפוסט הבא מהסוף** (Import next post from the end) beside Add recipe
in the cookbook header. The application runs the existing Instagram browser
scraper directly—no AI service, chat, or terminal command is involved.
Each click selects the oldest profile post by its publication timestamp, skipping
all stored posts, including hidden posts. Only the requested profile timeline is
used; unrelated feed links and DOM discovery order do not determine selection.
The browser must receive Instagram's explicit end-of-pagination signal before
selecting a post. A stalled or incomplete scan imports nothing. The configured profile,
credentials, and browser session are reused; the report limit does not limit
these individual imports.

Imports run in the background and may take several minutes while the scraper
scrolls the profile. The button shows progress and prevents overlapping jobs
across tabs. After success, use **Refresh cookbook** to see the post; the app
does not reload the page automatically while you may be editing. Failures and
an exhausted feed are shown in the page. Jobs time out after 30 minutes. A server
restart interrupts an active job; refresh the cookbook before retrying.

Compose includes Chromium and its system dependencies. For a host-run server,
install it with `uv run playwright install chromium`. Instagram credentials must
already be configured in the local `.env`; login challenges may still require
restoring a valid session. This button is available only on the hosted cookbook.
Opening a page never starts an import.

## Local application environment

Install Make and Docker with the Docker Compose plugin and start the Docker engine
(for example, Docker Desktop). Run the commands below from this directory.
Compose runs both the Python web application and PostgreSQL.

Build and start the application and PostgreSQL, waiting for both health checks:

```sh
make up
docker compose ps
```

Open [the cookbook](http://localhost:8765/lizapanelim_posts.html).
Set `APP_PORT` in `.env` to change the web port. `make up` rebuilds the
application image so Python code changes take effect.

The application mounts this checkout at `/data`, preserving imported recipes,
and generated pages on the host. Shopping-list changes are stored in the
PostgreSQL volume. The server generates pages from database posts on startup;
Compose enables `--reload`, which polls for database and renderer changes every
second. Recipe order follows `reverse` in the served directory’s `cookbook.toml`:
`true` displays oldest first and `false` displays newest first (also the default
when no configuration file exists). Reload mode also picks up ordering changes.
Without `--reload`, restart the server to regenerate pages. An empty
database produces an empty cookbook. Generated pages prefer existing images in
`lizapanelim_posts_assets` over external image URLs stored in the database. Legacy post JSON files are never read or
modified by the server; import them before switching to database-backed pages. Existing `.env` settings remain available to the
server. This is a local development setup; the web server serves this directory.

Compose defaults to database `cookbook`, user `cookbook`, password
`cookbook_dev`, and host port `5432`. These credentials are for local
development. The port is bound only to `127.0.0.1`.

To customize these values, copy `.env.example` to `.env` if you do not already
have one. Otherwise, add the PostgreSQL settings to your existing `.env`,
preserving your other credentials. Compose reads `.env` automatically and
passes only the three PostgreSQL initialization variables to the container.
If port `5432` is occupied, set `POSTGRES_PORT` to another port, such as `5433`.

The matching connection URL for a host application is:

```text
postgresql://cookbook:cookbook_dev@127.0.0.1:5432/cookbook
```

Keep `DATABASE_URL` in sync when changing the user, password, port, or database;
URL-encode special characters in credentials. The application uses SQLAlchemy
with the psycopg driver, so host URLs should use the
`postgresql+psycopg://` scheme. The Compose application receives an equivalent
URL that connects to `postgres:5432` inside the Compose network.

Schema changes are version-controlled with Alembic. The app applies pending
migrations before starting; the initial migration only establishes Alembic's
version record and does not create recipe tables or touch the file-backed data.
For a host-run migration, load the environment and run:

```sh
uv run alembic -c pyproject.toml upgrade head
```

After that, import the existing durable per-post JSON store once. The command
is idempotent: it adds missing shortcodes and never overwrites existing rows.
After this one-time import, normal `cookbook` runs use PostgreSQL as the post
source of truth. They still generate JSON and HTML report files for the static
web UI, but those files are not read back as post data.

The schema also includes `ingredients` (one row per ingredient) and
`shopping_list` (one row per item, referencing an ingredient, with optional
quantity and checked status). Shopping items are displayed alphabetically;
there is no stored position. A separate revision record protects list updates. The shopping-list API now
reads and writes PostgreSQL. Before starting the updated server, apply migrations
and import your existing list once (load `DATABASE_URL` from your environment):

```sh
uv run alembic -c pyproject.toml upgrade head
uv run cookbook-import-shopping-list --file shopping_list.json
```

The import retains the JSON file and refuses to run once list storage is initialized,
including after an empty import or after the shopping list has been cleared. Normal server operation
never reads or writes that legacy file. An empty database returns an empty list;
browser-only lists should be backed up before switching to the database server.
Database save failures are shown in the UI, with a browser-local backup retained.
Hosted shopping pages preserve the original browser list and save recovery copies
under `cookbook-shopping-list-backup-<timestamp>`. They disable editing if the
initial database read fails. Saves are queued, and a stale tab receives a conflict
instead of overwriting a newer list. Reload after an error before saving again.
The shopping API returns `{ "items": [...], "revision": N }`; PUT requires the
same shape and returns the next revision. Old pages must be refreshed after upgrade.

If legacy titles exist separately, import them explicitly:

```sh
uv run cookbook-import-post-store --store lizapanelim_posts_items --titles lizapanelim_posts_titles.json
```

Titles are applied to new posts and fill blank titles on existing posts; existing
nonblank database titles and recipe overrides remain authoritative. The source
files are retained. Normal imports no longer use legacy file-storage helpers,
and report generation retains cached images even in strict window mode.


Recipe edits, custom recipes, ingredients entered in recipes, preparation links,
and notes now share database storage through `/api/recipe-state`. This migration
retains the existing browser state format in a versioned JSON record, separate
from scraped posts. Apply pending migrations before starting the updated server.
On the first visit, an unused database imports recipe changes from that browser's
`cookbook-recipe-changes-v1` local storage. Open the cookbook first in the browser
containing the edits you want to migrate. Once initialized, the database is the
source of truth, including after custom recipes are deleted. Other browsers'
legacy copies are retained but are not automatically merged.

To import a saved browser copy explicitly before opening the hosted cookbook,
save the JSON value of `cookbook-recipe-changes-v1` (or one of its backup keys)
from the browser's developer tools under Application/Storage → Local Storage
to a UTF-8 file. The file must contain the state object with `overrides`,
`custom`, and optional `order`, without an extra wrapper or surrounding quotes.
Then run:

```sh
uv run cookbook-import-recipe-state --file recipe-state.json
```

The command loads `.env`, validates the entire file before writing, retains
the source file, and refuses to overwrite any initialized recipe state—even
an intentionally empty state. Apply pending migrations first. This also lets
you migrate edits from a `file://` cookbook by exporting its local storage.
Keep exports and backups local; they contain your recipe edits and notes.

Both cookbook and notes pages save to the database. Save feedback appears beside
the edited field or form; success clears after two seconds and errors remain
visible. Opening the cookbook does not save unchanged recipe state. Concurrent edits from a
stale tab are rejected: reload before editing again. Save failures are displayed
on the page; unsaved changes are retained in browser storage under
`cookbook-recipe-changes-v1-backup-<timestamp>`. The original browser copy is
never overwritten by hosted pages. Opening exported pages through `file://`
continues to use browser-only storage. Database snapshots cover the entire
recipe editing state, so concurrent edits to different recipes also conflict.

Import recipe posts separately:

```sh
uv run cookbook-import-post-store --store lizapanelim_posts_items
```

Verify a SQL connection or open an interactive shell:

```sh
docker compose exec postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database(), current_user;"'
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Inspect logs and stop the environment:

```sh
docker compose logs postgres
make down
```

The `postgres_data` named volume retains data when containers are stopped or
removed with `make down`. Run `make up` to start
again with the same data. `docker compose down --volumes` deletes the database
data; use it only when intentionally resetting the development database.

Initialization settings apply only to an empty volume. Changing credentials
in `.env` does not update an existing database's credentials.

The image is pinned to PostgreSQL version 18.6. Its volume is mounted at
`/var/lib/postgresql`, following the [official image's storage layout](https://hub.docker.com/_/postgres).
Major-version upgrades require a database migration, not just changing the tag.

## Migration verification and backups

Before updating an existing installation, retain a PostgreSQL backup and browser
exports. Keep the original post JSON, title files, and cached images until you
have verified your data. `make up` applies pending migrations automatically.

```sh
mkdir -p .private-backups
chmod 700 .private-backups
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > .private-backups/cookbook.dump
uv run pytest
# Exercise migrations, concurrency, and reconnect persistence in a disposable schema:
docker compose exec -T -e PYTHONPATH=/data/src app python /data/scripts/verify_postgres_migration.py
```

The verification script requires permission to create a schema and drops only its
own randomly named test schema. Browser tests require Chromium:
`uv run playwright install chromium`. Test saves never modify the live cookbook.
To inspect a backup without restoring it, run `pg_restore --list` against it.
Restore backups into a separate database first, verify the data, then intentionally
switch `DATABASE_URL`; never restore over the working database as a routine check.

The local web server serves only cookbook pages, the favicon, and cached images.
Credentials, source JSON, and private backups are not served over HTTP.
