"""Download recipe photos from Instagram and keep them in the database."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session, sessionmaker

from .models import Recipe
from .recipe_photo_repository import insert_recipe_photo, photo_ids

PHOTO_CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def download_photo(recipe: Recipe) -> tuple[bytes, str] | None:
    """Fetch a recipe's photo, trying Instagram's media endpoints if its URL has expired."""

    image_url = recipe.image_url.strip()
    suffix = Path(urlsplit(image_url).path).suffix.lower()
    content_type = PHOTO_CONTENT_TYPES.get(suffix, "image/jpeg")
    candidate_urls = [image_url]
    if recipe.post is not None:
        path_type = "reel" if recipe.post.is_video else "p"
        candidate_urls += [
            f"https://www.instagram.com/{path_type}/{recipe.post.shortcode}/media/?size=l",
            f"https://www.instagram.com/{path_type}/{recipe.post.shortcode}/media/?size=m",
        ]
    for candidate_url in candidate_urls:
        request = Request(
            candidate_url,
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
            continue
        if content:
            return content, content_type
    return None


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
        if not recipe.image_url.strip().startswith("http"):
            continue
        photo = download_photo(recipe)
        if photo is not None and insert_recipe_photo(factory, recipe.id, photo[1], photo[0]):
            count += 1
    return count
