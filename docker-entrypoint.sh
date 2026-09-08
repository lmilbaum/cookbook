#!/bin/sh
set -eu

# Apply only version-controlled migrations.  The baseline adds no cookbook
# tables, so this cannot import, rewrite, or remove the existing file data.
alembic -c /app/pyproject.toml upgrade head

# A fresh checkout can serve an empty cookbook before the first import.
if [ ! -f /data/lizapanelim_posts.json ]; then
    printf '[]\n' > /data/lizapanelim_posts.json
fi

exec cookbook-server --host 0.0.0.0 --port 8765 --directory /data --no-open --reload
