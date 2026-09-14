"""Read only profile timeline pagination observed by the Instagram browser."""
from __future__ import annotations

import re
from typing import Any


class ProfileTimeline:
    """Keep publication order separate from DOM discovery and suggested feeds."""

    connection_key = "xdt_api__v1__feed__user_timeline_graphql_connection"

    def __init__(self) -> None:
        self.posts: dict[str, tuple[int, str]] = {}
        self.complete = False
        self.invalid = False

    def observe(self, response: Any) -> None:
        if "graphql" not in response.url:
            return
        try:
            self.consume(response.json())
        except (ValueError, TypeError):
            # Other GraphQL responses need not be JSON timeline pages.
            return
        except Exception:
            # A failed response must never turn a partial scan into a complete one.
            return

    def consume(self, payload: object) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return
        connection = payload["data"].get(self.connection_key)
        if not isinstance(connection, dict):
            return
        if payload.get("errors"):
            self.invalid = True
            return
        edges, info = connection.get("edges"), connection.get("page_info")
        if not isinstance(edges, list) or not isinstance(info, dict):
            self.invalid = True
            return
        if type(info.get("has_next_page")) is not bool:
            self.invalid = True
            return
        for edge in edges:
            node = edge.get("node") if isinstance(edge, dict) else None
            if not isinstance(node, dict):
                self.invalid = True
                continue
            code, timestamp = node.get("code"), node.get("taken_at")
            if (not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", code)
                or type(timestamp) is not int or timestamp <= 0):
                self.invalid = True
                continue
            kind = "reel" if node.get("product_type") == "clips" else "p"
            self.posts[code] = (timestamp, f"/{kind}/{code}/")
        if info["has_next_page"] is False and not self.invalid:
            self.complete = True

    def paths(self) -> list[str]:
        """Return newest-first paths, regardless of pinning or response order."""
        return [path for _, path in sorted(self.posts.values(), reverse=True)]
