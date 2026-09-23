"""Why a profile scan can end incomplete, keyed by a code the UI can localize."""

from __future__ import annotations

# The English text is for logs and API clients; the page shows a translation of the code.
REASONS: dict[str, str] = {
    "pagination_incomplete": "Profile pagination data was incomplete; no post selected.",
    "pagination_unconfirmed": "Instagram did not confirm the profile pagination end; no post selected.",
    "scroll_limit": "Profile scrolling reached its safety limit; no post selected.",
    "feed_end_not_found": "Profile scrolling reached its safety limit before finding the feed end; no post selected.",
}
