"""Turn ytmusicapi's answers into small, validated items for the dashboard's player.

Everything here is data from YouTube that ends up in a browser, so IDs are checked against
strict patterns and artwork URLs are only kept for Google's image hosts (the dashboard's CSP
allows exactly these).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from echo_tunes.tokens import is_video_id

Kind = Literal["song", "album", "playlist", "artist"]
KINDS: tuple[Kind, ...] = ("song", "album", "playlist", "artist")
# What the player can search for: YouTube Music's kinds, or "video" for all of YouTube (its
# results are songs: a video plays like any other song).
SearchKind = Literal["song", "album", "playlist", "artist", "video"]
SEARCH_FILTERS: dict[str, str] = {
    "song": "songs",
    "album": "albums",
    "playlist": "playlists",
    "artist": "artists",
}
IMAGE_HOSTS = frozenset(
    {"i.ytimg.com", "lh3.googleusercontent.com", "yt3.ggpht.com", "yt3.googleusercontent.com"}
)
_LIST_ID = re.compile(r"[A-Za-z0-9_-]{2,80}", re.ASCII)
_PARAMS = re.compile(r"[A-Za-z0-9_%=-]{4,300}", re.ASCII)
MAX_ITEMS = 40  # per row or result list


def is_list_id(value: str) -> bool:
    """A playlist, album or artist ID (browse or playlist ID)."""
    return bool(_LIST_ID.fullmatch(value))


def is_mood_params(value: str) -> bool:
    return bool(_PARAMS.fullmatch(value))


@dataclass(frozen=True, slots=True)
class Item:
    kind: Kind
    id: str  # video ID for songs; playlist ID, album browse ID or artist channel ID otherwise
    title: str
    subtitle: str = ""
    image: str | None = None
    duration: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def image(thumbnails: list[dict[str, Any]] | None, prefer: int = 300) -> str | None:
    """The smallest thumbnail at least ``prefer`` px wide (else the largest), on a known host."""
    good = []
    for t in thumbnails or []:
        url = str(t.get("url") or "")
        parts = urlsplit(url)
        if parts.scheme == "https" and parts.hostname in IMAGE_HOSTS:
            good.append((int(t.get("width") or 0), url))
    if not good:
        return None
    good.sort()
    url = next((u for w, u in good if w >= prefer), good[-1][1])
    # Google's image URLs carry the size: ask for a sharper one instead of upscaling 120 px.
    return _SIZED.sub(f"=w{prefer}-h{prefer}", url) if "googleusercontent" in url else url


_SIZED = re.compile(r"=w\d{2,4}-h\d{2,4}")


def _artists(item: dict[str, Any]) -> str:
    names = [a.get("name", "") for a in item.get("artists") or [] if a and a.get("name")]
    return ", ".join(names[:2])


def text(value: Any, limit: int = 200) -> str:
    return " ".join(str(value or "").split())[:limit]


def parse(raw: dict[str, Any]) -> Item | None:
    """One search result, chart, home-page or library entry; None if it isn't playable."""
    if not isinstance(raw, dict):
        return None
    thumbs = raw.get("thumbnails")
    vid = raw.get("videoId")
    kind = raw.get("resultType")
    if vid and (kind in (None, "song", "video")):
        if not is_video_id(str(vid)) or raw.get("isAvailable") is False:
            return None
        album = (raw.get("album") or {}).get("name") if isinstance(raw.get("album"), dict) else ""
        return Item(
            "song",
            str(vid),
            text(raw.get("title")) or "Unknown",
            _artists(raw) or text(album),
            image(thumbs),
            raw.get("duration_seconds") or raw.get("lengthSeconds"),
        )
    if kind == "artist" or str(raw.get("browseId") or "").startswith("UC"):
        bid = str(raw.get("browseId") or "")
        if not is_list_id(bid):
            return None
        name = text(raw.get("artist") or raw.get("title"))
        return Item("artist", bid, name, "Artist", image(thumbs))
    if kind == "album" or str(raw.get("browseId") or "").startswith("MPRE"):
        bid = str(raw.get("browseId") or "")
        if not is_list_id(bid):
            return None
        sub = " · ".join(x for x in (_artists(raw), text(raw.get("year"))) if x)
        return Item("album", bid, text(raw.get("title")), sub or "Album", image(thumbs))
    pid = str(raw.get("playlistId") or raw.get("browseId") or "")
    pid = pid.removeprefix("VL")  # search returns the browse form "VL<playlist ID>"
    if pid and is_list_id(pid):
        sub = text(raw.get("author") or raw.get("description"), 80)
        if isinstance(raw.get("author"), list):
            sub = ", ".join(text(a.get("name")) for a in raw["author"] if isinstance(a, dict))
        return Item("playlist", pid, text(raw.get("title")), sub or "Playlist", image(thumbs))
    return None


def parse_all(raws: Any, limit: int = MAX_ITEMS) -> list[Item]:
    items: list[Item] = []
    seen: set[tuple[str, str]] = set()
    for raw in raws or []:
        item = parse(raw)
        if item is not None and (item.kind, item.id) not in seen:
            seen.add((item.kind, item.id))
            items.append(item)
            if len(items) >= limit:
                break
    return items


def sections(home: Any, limit: int = 8) -> list[dict[str, Any]]:
    """The home page's titled rows (Quick picks, mixes, playlists...)."""
    out = []
    for section in home or []:
        items = parse_all((section or {}).get("contents"), 20)
        if items:
            out.append({"title": text(section.get("title"), 80), "items": items})
        if len(out) >= limit:
            break
    return out
