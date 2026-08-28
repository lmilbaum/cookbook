"""Shared data models for cookbook scraping/export workflows."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PostItem:  # pylint: disable=too-many-instance-attributes
    """Serializable post data exported to JSON and HTML reports."""

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
