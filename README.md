# Cookbook

Python tools for importing recipes and serving a personal cookbook.
See [QUICK_START.md](QUICK_START.md) for scraper instructions.

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
generated pages, and shopping-list changes on the host. An empty recipe data
file is created only if none exists. The server regenerates pages on startup
and when recipe data changes. Existing `.env` settings remain available to the
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
