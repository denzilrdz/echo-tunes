"""Search all of YouTube (not just YouTube Music): "play ... on YouTube" and the player's
YouTube tab.

yt-dlp does the searching inside the resolver's worker processes (no API key, no quota). What
comes back is data from YouTube that ends up in a browser, so every field is checked here, the
same way ``browse`` checks YouTube Music's answers. Live streams are left out: YouTube only
offers them as HLS, which the Echo's audio relay can't play.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from echo_tunes.cache import BoundedTTLCache
from echo_tunes.music import browse
from echo_tunes.tokens import is_video_id

RESULTS = 20  # asked for per search; the player shows them all, a voice request plays the first
# The whole search, waiting for a free worker included: Alexa allows ~8 s for the answer.
BUDGET = 6.5
_NOT_PLAYABLE = frozenset({"is_live", "is_upcoming", "post_live"})

Search = Callable[[str, int], Awaitable[list[dict[str, Any]]]]


def parse(raw: Any) -> browse.Item | None:
    """One flat yt-dlp search entry as a playable item; None for live streams and junk."""
    if not isinstance(raw, dict):
        return None
    vid = str(raw.get("id") or "")
    if not is_video_id(vid) or raw.get("live_status") in _NOT_PLAYABLE:
        return None
    duration = raw.get("duration")
    if not isinstance(duration, (int, float)) or duration <= 0:
        return None  # no length: live, or not a video at all
    channel = browse.text(raw.get("channel") or raw.get("uploader"), 80)
    thumbs = raw.get("thumbnails") if isinstance(raw.get("thumbnails"), list) else None
    return browse.Item(
        "song",
        vid,
        browse.text(raw.get("title")) or "Unknown",
        channel,
        browse.image(thumbs),
        int(duration),
    )


def parse_all(raws: Any, limit: int = RESULTS) -> list[browse.Item]:
    items: list[browse.Item] = []
    seen: set[str] = set()
    for raw in raws if isinstance(raws, list) else []:
        item = parse(raw)
        if item is not None and item.id not in seen:
            seen.add(item.id)
            items.append(item)
            if len(items) >= limit:
                break
    return items


def clean_query(query: str) -> str:
    """One line of plain text, at most 100 characters."""
    return " ".join(query.split())[:100]


class YouTubeSearch:
    def __init__(self, search: Search) -> None:
        self._search = search
        self._cache: BoundedTTLCache[str, list[browse.Item]] = BoundedTTLCache(128, ttl=900)

    async def search(self, query: str) -> list[browse.Item]:
        q = clean_query(query)
        if not q:
            return []
        key = q.lower()
        cached = self._cache.get(key)
        if cached is None:
            async with asyncio.timeout(BUDGET):
                cached = parse_all(await self._search(q, RESULTS))
            self._cache.set(key, cached)
        return cached
