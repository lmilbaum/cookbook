"""Recipe post models for file-backed and database-backed workflows."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Post(Base):
    """Database-backed recipe post, identified by its Instagram shortcode."""

    __tablename__ = "posts"

    shortcode: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(Text)
    caption: Mapped[str] = mapped_column(Text)
    timestamp_utc: Mapped[str] = mapped_column(String(64), index=True)
    likes: Mapped[int] = mapped_column(Integer)
    comments: Mapped[int] = mapped_column(Integer)
    typename: Mapped[str] = mapped_column(String(128))
    is_video: Mapped[bool] = mapped_column(Boolean)
    title: Mapped[str] = mapped_column(Text, default="")
    recipe_url: Mapped[str] = mapped_column(Text, default="")
    recipe_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    recipe_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_recipe: Mapped[bool] = mapped_column(Boolean, default=True)


@dataclass
class PostItem:  # pylint: disable=too-many-instance-attributes
    """Temporary JSON-store representation used during the database migration."""

    shortcode: str
    url: str
    image_url: str
    caption: str
    timestamp_utc: str
    likes: int
    comments: int
    typename: str
    is_video: bool
    title: str = ""
    recipe_url: str = ""
    recipe_urls: list[str] = field(default_factory=list)
    recipe_names: list[str] = field(default_factory=list)
