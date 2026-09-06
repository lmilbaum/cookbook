#!/bin/sh
set -eu

# A fresh checkout can serve an empty cookbook before the first import.
if [ ! -f /data/lizapanelim_posts.json ]; then
    printf '[]\n' > /data/lizapanelim_posts.json
fi

exec cookbook-server --host 0.0.0.0 --port 8765 --directory /data --no-open --reload
