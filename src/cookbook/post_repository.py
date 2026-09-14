"""Database persistence for recipe posts."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import Post, PostItem


def item_from_post(post: Post) -> PostItem:
    """Convert an ORM post to the report and scraper representation."""

    return PostItem(
        shortcode=post.shortcode,
        url=post.url,
        image_url=post.image_url,
        caption=post.caption,
        timestamp_utc=post.timestamp_utc,
        likes=post.likes,
        comments=post.comments,
        typename=post.typename,
        is_video=post.is_video,
        title=post.title,
        recipe_url=post.recipe_url,
        recipe_urls=list(post.recipe_urls),
        recipe_names=list(post.recipe_names),
    )


def post_from_item(item: PostItem) -> Post:
    """Convert a scraper result to an ORM post."""

    return Post(
        shortcode=item.shortcode,
        url=item.url,
        image_url=item.image_url,
        caption=item.caption,
        timestamp_utc=item.timestamp_utc,
        likes=item.likes,
        comments=item.comments,
        typename=item.typename,
        is_video=item.is_video,
        title=item.title,
        recipe_url=item.recipe_url,
        recipe_urls=item.recipe_urls,
        recipe_names=item.recipe_names,
    )


def load_posts(factory: sessionmaker[Session], reverse: bool) -> list[PostItem]:
    """Return all database posts in the configured report ordering."""

    ordering = Post.timestamp_utc.asc() if reverse else Post.timestamp_utc.desc()
    with factory() as session:
        posts = session.scalars(
            select(Post).where(Post.is_recipe.is_(True)).order_by(ordering)
        ).all()
        return [item_from_post(post) for post in posts]


def insert_missing_posts(
    factory: sessionmaker[Session], items: Iterable[PostItem], titles: dict[str, str] | None = None
) -> int:
    """Insert new scraper results without replacing existing database rows."""

    inserted = 0
    with session_scope(factory) as session:
        for shortcode, title in (titles or {}).items():
            post = session.get(Post, shortcode)
            if post is not None and not post.title.strip() and title.strip():
                post.title = title.strip()
        for item in items:
            if session.get(Post, item.shortcode) is not None:
                continue
            session.add(post_from_item(item))
            inserted += 1
    return inserted


def mark_not_recipe(factory: sessionmaker[Session], shortcode: str) -> bool:
    """Hide a known non-recipe post from generated cookbook reports."""

    with session_scope(factory) as session:
        post = session.get(Post, shortcode)
        if post is None:
            return False
        post.is_recipe = False
    return True
