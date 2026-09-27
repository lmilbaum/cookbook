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
        self.skipped_edges: int = 0

    def observe(self, response: Any) -> None:
        if "graphql" not in response.url:
            return
        try:
            self.consume(response.json())
        except (ValueError, TypeError):
            # Other GraphQL responses need not be JSON timeline pages.
            return
        except Exception:  # noqa: BLE001
            # A failed response must never turn a partial scan into a complete one.
            return

    def consume(self, payload: object) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return
        connection = payload["data"].get(self.connection_key)
        if not isinstance(connection, dict):
            return
        if payload.get("errors"):
            print(f"Skipping GraphQL response with errors: {payload['errors']}")
            return
        edges, info = connection.get("edges"), connection.get("page_info")
        if not isinstance(edges, list) or not isinstance(info, dict):
            return
        if type(info.get("has_next_page")) is not bool:
            return
        # A malformed node is skipped; only page-level errors make the pagination state untrustworthy.
        for edge in edges:
            node = edge.get("node") if isinstance(edge, dict) else None
            if not isinstance(node, dict):
                self.skipped_edges += 1
                continue
            code, timestamp = node.get("code"), node.get("taken_at")
            if (not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", code)
                or type(timestamp) is not int or timestamp <= 0):
                self.skipped_edges += 1
                continue
            kind = "reel" if node.get("product_type") == "clips" else "p"
            self.posts[code] = (timestamp, f"/{kind}/{code}/")
        if info["has_next_page"] is False:
            self.complete = True

    def paths(self) -> list[str]:
        """Return newest-first paths, regardless of pinning or response order."""
        return [path for _, path in sorted(self.posts.values(), reverse=True)]
