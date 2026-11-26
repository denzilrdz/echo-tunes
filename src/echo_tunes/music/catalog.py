"""Search, radio and (when signed in) your library, from YouTube Music via ytmusicapi."""

from __future__ import annotations

import asyncio
import difflib
import logging
import re
import threading
from dataclasses import dataclass
from typing import Any, Protocol

from echo_tunes.cache import BoundedTTLCache
from echo_tunes.tokens import is_video_id

log = logging.getLogger(__name__)

LIBRARY_LIMIT = 200  # songs taken from a playlist or liked songs


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


@dataclass(frozen=True, slots=True)
class Collection:
    """A named list of songs: a playlist, a mix, or liked songs."""

    title: str
    tracks: list[Track]


class NotSignedIn(Exception):
    """The request needs a YouTube Music account; see ``echo-tunes login``."""


class Catalog(Protocol):
    @property
    def signed_in(self) -> bool: ...
    async def search_song(self, query: str) -> Track | None: ...
    async def radio(self, video_id: str, limit: int) -> list[Track]: ...
    async def liked_songs(self) -> Collection: ...
    async def playlist(self, name: str) -> Collection | None: ...
    async def mix(self, name: str) -> Collection | None: ...
    async def like(self, video_id: str) -> None: ...
    async def played(self, video_id: str) -> None: ...


def _artists(item: dict[str, Any]) -> str:
    names = [a.get("name", "") for a in item.get("artists") or [] if a.get("name")]
    return ", ".join(names[:2])


def _track(item: dict[str, Any]) -> Track | None:
    vid = item.get("videoId")
    if not vid or not is_video_id(vid) or item.get("isAvailable") is False:
        return None
    return Track(
        video_id=vid,
        title=(item.get("title") or "Unknown").strip(),
        artist=_artists(item),
        duration=item.get("duration_seconds") or item.get("lengthSeconds"),
    )


def _tracks(items: list[dict[str, Any]] | None) -> list[Track]:
    return [t for t in map(_track, items or []) if t]


def normalise(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def best_match(wanted: str, names: list[str], cutoff: float = 0.55) -> int | None:
    """Index of the name that best matches what was said, tolerating speech-to-text slips."""
    want = normalise(wanted)
    norm = [normalise(n) for n in names]
    if want in norm:
        return norm.index(want)
    contains = [i for i, n in enumerate(norm) if want and (want in n or n in want) and n]
    if contains:
        return min(contains, key=lambda i: abs(len(norm[i]) - len(want)))
    close = difflib.get_close_matches(want, norm, n=1, cutoff=cutoff)
    return norm.index(close[0]) if close else None


class YTMusicCatalog:
    def __init__(self, client: Any, signed_in: bool, *, send_history: bool = False) -> None:
        self._yt = client
        self._signed_in = signed_in
        self._send_history = send_history and signed_in
        # ytmusicapi shares one HTTP session; calls are short, so serialise them.
        self._lock = threading.Lock()
        self._searches: BoundedTTLCache[str, Track] = BoundedTTLCache(256, ttl=3600)
        self._lists: BoundedTTLCache[str, list[dict[str, Any]]] = BoundedTTLCache(4, ttl=600)

    @property
    def signed_in(self) -> bool:
        return self._signed_in

    async def search_song(self, query: str) -> Track | None:
        key = normalise(query)
        cached = self._searches.get(key)
        if cached is not None:
            return cached
        results = await self._call("search", key, filter="songs", limit=5)
        track = next(iter(_tracks(results)), None)
        if track is not None:
            self._searches.set(key, track)
        return track

    async def radio(self, video_id: str, limit: int) -> list[Track]:
        data = await self._call("get_watch_playlist", videoId=video_id, radio=True, limit=limit)
        return _tracks((data or {}).get("tracks"))

    # --- your library (signed in) -----------------------------------------------------------
    async def liked_songs(self) -> Collection:
        self._need_account()
        data = await self._call("get_liked_songs", limit=LIBRARY_LIMIT)
        return Collection("your liked songs", _tracks((data or {}).get("tracks")))

    async def playlist(self, name: str) -> Collection | None:
        self._need_account()
        playlists = await self._cached_list("playlists", "get_library_playlists", limit=None)
        titles = [p.get("title", "") for p in playlists]
        i = best_match(name, titles)
        if i is None:
            return None
        data = await self._call("get_playlist", playlists[i]["playlistId"], limit=LIBRARY_LIMIT)
        return Collection(titles[i], _tracks((data or {}).get("tracks")))

    async def mix(self, name: str) -> Collection | None:
        """One of your personal mixes from the home page, e.g. "My Supermix", "Discover Mix"."""
        self._need_account()
        home = await self._cached_list("home", "get_home", limit=6)
        mixes = [
            item
            for section in home
            for item in section.get("contents") or []
            if item and item.get("playlistId") and "mix" in (item.get("title") or "").lower()
        ]
        if not mixes:
            return None
        wanted = name if "mix" in name.lower() else f"{name} mix"
        i = best_match(wanted, [m["title"] for m in mixes], cutoff=0.4)
        chosen = mixes[i if i is not None else 0]
        data = await self._call("get_watch_playlist", playlistId=chosen["playlistId"], limit=50)
        return Collection(chosen["title"], _tracks((data or {}).get("tracks")))

    async def like(self, video_id: str) -> None:
        self._need_account()
        from ytmusicapi import LikeStatus

        await self._call("rate_song", video_id, LikeStatus.LIKE)

    async def played(self, video_id: str) -> None:
        """Add a song to your YouTube history, so recommendations learn (opt-in)."""
        if not self._send_history:
            return
        try:
            song = await self._call("get_song", video_id)
            await self._call("add_history_item", song)
        except Exception as exc:
            log.info("couldn't add %s to history: %s", video_id, exc)

    # --- helpers --------------------------------------------------------------------------------
    def _need_account(self) -> None:
        if not self._signed_in:
            raise NotSignedIn

    async def _cached_list(self, key: str, method: str, **kwargs: Any) -> list[dict[str, Any]]:
        cached = self._lists.get(key)
        if cached is None:
            cached = list(await self._call(method, **kwargs) or [])
            self._lists.set(key, cached)
        return cached

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        def run() -> Any:
            with self._lock:
                return getattr(self._yt, method)(*args, **kwargs)

        return await asyncio.to_thread(run)
