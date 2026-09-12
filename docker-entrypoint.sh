#!/bin/sh
set -eu

# Apply version-controlled schema migrations before reading database posts.
alembic -c /app/pyproject.toml upgrade head

exec cookbook-server --host 0.0.0.0 --port 8765 --directory /data --no-open --reload
