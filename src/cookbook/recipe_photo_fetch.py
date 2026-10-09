"""Download recipe photos from Instagram and keep them in the database."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .models import Recipe
from .post_repository import load_recipes
from .recipe_photo_repository import insert_recipe_photo, photo_ids, replace_recipe_photo
from .recipe_state_repository import override_image_urls

PHOTO_CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _fetch(url: str) -> bytes | None:
    """Return the body of one photo URL, or ``None`` if it cannot be fetched."""

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            content = response.read()
    except OSError:
        return None
    return content or None


def download_photo(recipe: Recipe) -> tuple[bytes, str] | None:
    """Fetch a recipe's photo, trying Instagram's media endpoints if its URL has expired."""

    image_url = recipe.image_url.strip()
    suffix = Path(urlsplit(image_url).path).suffix.lower()
    content_type = PHOTO_CONTENT_TYPES.get(suffix, "image/jpeg")
    candidate_urls = [image_url] if image_url.startswith("http") else []
    if recipe.post is not None:
        path_type = "reel" if recipe.post.is_video else "p"
        candidate_urls += [
            f"https://www.instagram.com/{path_type}/{recipe.post.shortcode}/media/?size=l",
            f"https://www.instagram.com/{path_type}/{recipe.post.shortcode}/media/?size=m",
        ]
    for candidate_url in candidate_urls:
        content = _fetch(candidate_url)
        if content:
            return content, content_type
    return None


def download_image_url(url: str) -> tuple[bytes, str] | None:
    """Fetch one image URL without any Instagram fallback."""

    suffix = Path(urlsplit(url).path).suffix.lower()
    content_type = PHOTO_CONTENT_TYPES.get(suffix, "image/jpeg")
    content = _fetch(url)
    return (content, content_type) if content else None


def store_missing_photos(factory: sessionmaker[Session], recipes: Iterable[Recipe]) -> int:
    """Download and store photos for recipes that have none; return how many were stored."""

    stored = photo_ids(factory)
    count = 0
    for recipe in recipes:
        if recipe.id in stored:
            continue
        photo_bytes = getattr(recipe, "_photo_bytes", None)
        if photo_bytes is not None:
            photo_ct = getattr(recipe, "_photo_content_type", "image/jpeg")
            if insert_recipe_photo(factory, recipe.id, photo_ct, photo_bytes):
                count += 1
            continue
        if not recipe.image_url.strip().startswith("http") and recipe.post is None:
            continue
        photo = download_photo(recipe)
        if photo is not None and insert_recipe_photo(factory, recipe.id, photo[1], photo[0]):
            count += 1
    return count


class PhotoBackfill:
    """Cache missing card photos in the background, with per-URL retry backoff."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        refresh: Callable[[], None],
        *,
        clock: Callable[[], float] = time.monotonic,
        max_per_pass: int = 20,
        initial_retry: float = 600.0,
        max_retry: float = 86400.0,
    ) -> None:
        self._factory = factory
        self._refresh = refresh
        self._clock = clock
        self._max_per_pass = max_per_pass
        self._initial_retry = initial_retry
        self._max_retry = max_retry
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._pending_replacements: dict[str, str] = {}
        # (recipe_id, url) -> (next_attempt_at, delay)
        self._retry: dict[tuple[str, str], tuple[float, float]] = {}

    def request_replacements(self, urls: Mapping[str, str]) -> None:
        """Queue explicit re-downloads of recipe photos from new image URLs."""

        with self._lock:
            self._pending_replacements.update(urls)
        self._wake.set()

    def run_once(self) -> int:
        """Apply queued replacements and cache missing photos; return how many were written."""

        with self._lock:
            pending, self._pending_replacements = self._pending_replacements, {}

        written: set[str] = set()
        try:
            for recipe_id, url in pending.items():
                with self._factory() as session:
                    if session.get(Recipe, recipe_id) is None:
                        continue
                photo = download_image_url(url)
                if photo is not None:
                    data, content_type = photo
                    replace_recipe_photo(self._factory, recipe_id, content_type, data)
                    written.add(recipe_id)
        except SQLAlchemyError:
            with self._lock:
                for rid, url in pending.items():
                    self._pending_replacements.setdefault(rid, url)
            raise

        recipes = load_recipes(self._factory, reverse=False)
        urls = override_image_urls(self._factory)
        stored = photo_ids(self._factory)

        candidates: list[tuple[Recipe, str]] = []
        for recipe in recipes:
            if recipe.id in stored:
                continue
            effective_url = urls.get(recipe.id) or recipe.image_url.strip()
            if not effective_url.startswith("http"):
                continue
            if self._clock() < self._retry.get((recipe.id, effective_url), (0.0, 0.0))[0]:
                continue
            candidates.append((recipe, effective_url))
            if len(candidates) >= self._max_per_pass:
                break

        for recipe, effective_url in candidates:
            photo = download_photo(replace(recipe, image_url=effective_url))
            key = (recipe.id, effective_url)
            if photo is None:
                _, previous_delay = self._retry.get(key, (0.0, 0.0))
                delay = min(previous_delay * 2 if previous_delay else self._initial_retry, self._max_retry)
                self._retry[key] = (self._clock() + delay, delay)
                continue
            data, content_type = photo
            if insert_recipe_photo(self._factory, recipe.id, content_type, data):
                written.add(recipe.id)
            for retry_key in [k for k in self._retry if k[0] == recipe.id]:
                del self._retry[retry_key]

        if written:
            self._refresh()
        return len(written)

    def run_forever(self, interval: float = 300.0) -> None:
        """Run passes forever, waking early when replacements are requested."""

        while True:
            try:
                self.run_once()
            except SQLAlchemyError:
                print("Photo backfill: database unavailable; retrying later.", file=sys.stderr)
            except (OSError, TypeError, ValueError) as error:
                print(f"Photo backfill failed: {type(error).__name__}", file=sys.stderr)
            self._wake.wait(interval)
            self._wake.clear()
