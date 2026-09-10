# Cookbook contributor guide

## Project at a glance

- Python 3.11+ application for importing Instagram recipe posts and serving a
  local cookbook.
- Source code lives in `src/cookbook/`; tests live in `tests/`.
- Packaging and dependencies are defined in `pyproject.toml`; use `uv` for
  local Python commands.
- The local application stack is Docker Compose (web app plus PostgreSQL).

## Common commands

```sh
# Install/sync the development environment
uv sync

# Run the test suite
uv run pytest

# Run a focused test file
uv run pytest tests/test_report_html.py

# Run the command-line importer with the repository configuration
uv run cookbook --config cookbook.toml

# Start and stop the local web application and database
make up
make down
```

Use `uv run playwright install chromium` when working on the browser scraper
for the first time. Run pending local database migrations with
`uv run alembic -c pyproject.toml upgrade head`.

## Implementation conventions

- Keep modules typed using modern Python annotations and retain
  `from __future__ import annotations` in modules that already use it.
- Prefer standard-library facilities unless a project dependency is clearly
  warranted.
- Keep scraping, configuration, persistence, report rendering, and HTTP-server
  responsibilities in their existing modules rather than coupling them.
- Preserve user data: post JSON, titles, notes, shopping lists, generated HTML,
  and cached assets are application data. Do not delete, rename, or regenerate
  it unintentionally.
- Treat credentials, sessions, `.env`, and scraper output as sensitive/local;
  never commit them or expose their contents in logs/tests.
- Add or update focused `pytest` coverage for behavior changes, especially for
  file-backed data and rendered HTML.

## Database and containers

- Alembic migrations belong in `migrations/versions/`; never edit an existing
  applied migration—add a new revision instead.
- `make up` rebuilds the application image and waits for health checks.
- `make down` retains the PostgreSQL volume. Do not run Compose with
  `--volumes` unless an intentional database reset is requested.

## Before handing off changes

- Run the smallest relevant test first, then `uv run pytest` when practical.
- Check `git diff --check` and ensure only intended files changed.
- Update `README.md`, `QUICK_START.md`, or `BROWSER_SCRAPER.md` when commands,
  configuration, or user-facing behavior changes.
