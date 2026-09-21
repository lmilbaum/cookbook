"""Recipe post models for file-backed and database-backed workflows."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import (
    Mapped,
    MappedAsDataclass,
    mapped_column,
    relationship,
)

from .database import Base


class Ingredient(Base):
    """An ingredient reusable across shopping items."""

    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)


class RecipeType(Base):
    """A recipe type (salad, cake, soup...) that recipes and searches can use."""

    __tablename__ = "recipe_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)


class ShoppingListItem(Base):
    """One item in the single shared shopping list."""

    __tablename__ = "shopping_list_items"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[str | None] = mapped_column(Text)
    done: Mapped[bool] = mapped_column(Boolean, default=False)


class Recipe(MappedAsDataclass, Base, kw_only=True):
    """A recipe, optionally sourced from an Instagram post."""

    __tablename__ = "recipes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    image_url: Mapped[str] = mapped_column(Text)
    caption: Mapped[str] = mapped_column(Text)
    timestamp_utc: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    recipe_url: Mapped[str] = mapped_column(Text, default="")
    recipe_name: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="lizapanelim")
    # One-directional on purpose: a Post -> Recipe back-reference would make
    # dataclasses.asdict()/equality recurse Recipe.post.recipe.post... forever.
    #
    # Not a real foreign key: a rejected recipe is deleted while its post is
    # kept (so the importer's dedup still treats the shortcode as seen), so a
    # post can outlive the recipe it once matched.
    post: Mapped[Post | None] = relationship(
        primaryjoin="Recipe.id == foreign(Post.shortcode)",
        passive_deletes="all",
        default=None,
    )


class Post(MappedAsDataclass, Base, kw_only=True):
    """Instagram post metadata for a recipe, when it was scraped from Instagram."""

    __tablename__ = "posts"

    shortcode: Mapped[str] = mapped_column(Text, primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    typename: Mapped[str] = mapped_column(String(128))
    is_video: Mapped[bool] = mapped_column(Boolean)
    is_recipe: Mapped[bool] = mapped_column(Boolean, default=True)


class RecipeState(Base):
    """Shared recipe overrides and custom recipes in the browser's format."""

    __tablename__ = "recipe_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ShoppingListState(Base):
    """Revision and durable initialization marker for the shared list."""

    __tablename__ = "shopping_list_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)


class RecipePage(Base):
    """Full standalone recipe page, keyed by its URL slug."""

    __tablename__ = "recipe_pages"

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    html: Mapped[str] = mapped_column(Text)


class RecipeImage(Base):
    """An image referenced by a recipe page, keyed by its filename."""

    __tablename__ = "recipe_images"

    filename: Mapped[str] = mapped_column(Text, primary_key=True)
    content_type: Mapped[str] = mapped_column(Text)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class RecipePhoto(Base):
    """The cached photo shown on a recipe card, keyed by recipe id.

    Not a foreign key: like posts, a photo may outlive its recipe.
    """

    __tablename__ = "recipe_photos"

    recipe_id: Mapped[str] = mapped_column(Text, primary_key=True)
    content_type: Mapped[str] = mapped_column(Text)
    data: Mapped[bytes] = mapped_column(LargeBinary)
