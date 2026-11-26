"""Search and radio, from YouTube Music via ytmusicapi."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any, Protocol

from echo_tunes.cache import BoundedTTLCache
from echo_tunes.tokens import is_video_id

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Track:
    video_id: str
    title: str
    artist: str
    duration: int | None = None

    @property
    def spoken(self) -> str:
        return f"{self.title} by {self.artist}" if self.artist else self.title

    def to_dict(self) -> dict[str, Any]:
        return {"v": self.video_id, "t": self.title, "a": self.artist, "d": self.duration}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Track:
        return cls(video_id=d["v"], title=d["t"], artist=d["a"], duration=d.get("d"))


class Catalog(Protocol):
    async def search_song(self, query: str) -> Track | None: ...
    async def radio(self, video_id: str, limit: int) -> list[Track]: ...


def _artists(item: dict[str, Any]) -> str:
    names = [a.get("name", "") for a in item.get("artists") or [] if a.get("name")]
    return ", ".join(names[:2])


def _track(item: dict[str, Any]) -> Track | None:
    vid = item.get("videoId")
    if not vid or not is_video_id(vid):
        return None
    return Track(
        video_id=vid,
        title=(item.get("title") or "Unknown").strip(),
        artist=_artists(item),
        duration=item.get("duration_seconds") or item.get("lengthSeconds"),
    )


class YTMusicCatalog:
    def __init__(self, language: str = "en", location: str = "") -> None:
        from ytmusicapi import YTMusic

        self._yt = YTMusic(language=language, location=location)
        # ytmusicapi shares one HTTP session; calls are short, so serialise them.
        self._lock = threading.Lock()
        self._searches: BoundedTTLCache[str, Track | None] = BoundedTTLCache(256, ttl=3600)

    async def search_song(self, query: str) -> Track | None:
        key = " ".join(query.lower().split())
        if key in self._searches:
            return self._searches.get(key)
        results = await asyncio.to_thread(self._call, "search", key, filter="songs", limit=5)
        track = next((t for t in map(_track, results or []) if t), None)
        self._searches.set(key, track)
        return track

    async def radio(self, video_id: str, limit: int) -> list[Track]:
        data = await asyncio.to_thread(
            self._call, "get_watch_playlist", videoId=video_id, radio=True, limit=limit
        )
        return [t for t in map(_track, (data or {}).get("tracks", [])) if t]

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return getattr(self._yt, method)(*args, **kwargs)
