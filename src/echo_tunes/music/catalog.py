"""Search, radio and (when signed in) your library, from YouTube Music via ytmusicapi."""

from __future__ import annotations

import asyncio
import difflib
import logging
import re
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast

from echo_tunes.cache import BoundedTTLCache
from echo_tunes.music import browse
from echo_tunes.tokens import is_video_id

log = logging.getLogger(__name__)
T = TypeVar("T")

LIBRARY_LIMIT = 200  # songs taken from a playlist or liked songs
# Alexa gives a skill about 8 seconds to answer, so no YouTube Music call may take longer than
# this (the HTTP session also has its own timeout, see account.TimeoutSession).
CALL_TIMEOUT = 5.0


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
        # Its own small thread pool: a slow YouTube never starves other work, and calls run
        # side by side instead of queueing behind one another.
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ytmusic")
        self._searches: BoundedTTLCache[str, Track] = BoundedTTLCache(256, ttl=3600)
        self._lists: BoundedTTLCache[str, list[dict[str, Any]]] = BoundedTTLCache(4, ttl=600)
        # Browsing results for the player (search, charts, moods, home): small and short-lived.
        self._browsed: BoundedTTLCache[str, Any] = BoundedTTLCache(128, ttl=900)

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
        titles = [m["title"] for m in mixes]
        i = best_match(wanted, titles, cutoff=0.6)
        if i is None:
            if normalise(name) not in ("mix", "my mix", "supermix", "my supermix"):
                return None  # asked for a specific mix that isn't there: say so
            i = next((k for k, t in enumerate(titles) if "supermix" in t.lower()), 0)
        chosen = mixes[i]
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

    # --- browsing, for the dashboard's player -------------------------------------------------
    async def search_items(self, query: str, kind: browse.Kind) -> list[browse.Item]:
        key = f"search:{kind}:{normalise(query)}"
        return await self._browse(
            key,
            lambda: self._call(
                "search", query, filter=browse.SEARCH_FILTERS[kind], limit=browse.MAX_ITEMS
            ),
            browse.parse_all,
        )

    async def home(self) -> list[dict[str, Any]]:
        """Home-page rows: quick picks, mixes and playlists (personal when signed in)."""
        return await self._browse("home", lambda: self._call("get_home", limit=6), browse.sections)

    async def charts(self, country: str) -> dict[str, Any]:
        """Trending: chart playlists for the country, and its top artists."""

        def shape(c: Any) -> dict[str, Any]:
            c = c or {}
            lists = [*(c.get("videos") or []), *(c.get("languages") or [])]
            return {
                "playlists": browse.parse_all(lists, 20),
                "artists": browse.parse_all(c.get("artists"), 20),
            }

        code = country.upper() if re.fullmatch(r"[A-Za-z]{2}", country or "") else "ZZ"
        return await self._browse(f"charts:{code}", lambda: self._call("get_charts", code), shape)

    async def moods(self) -> list[dict[str, Any]]:
        """Moods & genres: sections of named categories, each opened with its params."""

        def shape(m: Any) -> list[dict[str, Any]]:
            out = []
            for title, cats in (m or {}).items():
                chips = [
                    {"title": str(c.get("title", ""))[:60], "params": c["params"]}
                    for c in cats or []
                    if isinstance(c, dict) and browse.is_mood_params(str(c.get("params", "")))
                ][:60]
                if chips:
                    out.append({"title": str(title)[:60], "categories": chips})
            return out

        return await self._browse("moods", lambda: self._call("get_mood_categories"), shape)

    async def mood_playlists(self, params: str) -> list[browse.Item]:
        if not browse.is_mood_params(params):
            return []
        return await self._browse(
            f"mood:{params}", lambda: self._call("get_mood_playlists", params), browse.parse_all
        )

    async def library_playlists(self) -> list[browse.Item]:
        self._need_account()
        liked = browse.Item("playlist", "LM", "Liked songs", "Your likes")
        lists = await self._cached_list("playlists", "get_library_playlists", limit=None)
        return [liked, *(i for i in browse.parse_all(lists) if i.id != "LM")]

    async def items_of(self, kind: browse.Kind, item_id: str) -> tuple[str, list[Track]]:
        """The songs behind an item: a playlist, album, artist's top songs, or a song's radio."""
        if kind == "song":
            if not is_video_id(item_id):
                raise ValueError("bad video ID")
            return "Radio", await self.radio(item_id, 25)
        if not browse.is_list_id(item_id):
            raise ValueError("bad ID")
        if kind == "playlist":
            if item_id == "LM":
                liked = await self.liked_songs()
                return "Liked songs", liked.tracks
            if item_id.startswith("RD"):  # mixes and radios
                data = await self._call("get_watch_playlist", playlistId=item_id, limit=50)
                return "Mix", _tracks((data or {}).get("tracks"))
            data = await self._call("get_playlist", item_id, limit=LIBRARY_LIMIT)
            return str((data or {}).get("title") or "Playlist"), _tracks((data or {}).get("tracks"))
        if kind == "album":
            data = await self._call("get_album", item_id)
            artist = _artists(data or {})
            tracks = [
                t if t.artist else Track(t.video_id, t.title, artist, t.duration)
                for t in _tracks((data or {}).get("tracks"))
            ]
            return str((data or {}).get("title") or "Album"), tracks
        data = await self._call("get_artist", item_id)
        songs = ((data or {}).get("songs") or {}).get("results")
        return str((data or {}).get("name") or "Artist"), _tracks(songs)

    async def _browse(
        self, key: str, fetch: Callable[[], Awaitable[Any]], shape: Callable[[Any], T]
    ) -> T:
        cached = self._browsed.get(key)
        if cached is None:
            cached = shape(await fetch())
            self._browsed.set(key, cached)
        return cast(T, cached)

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
        loop = asyncio.get_running_loop()
        fn = getattr(self._yt, method)
        async with asyncio.timeout(CALL_TIMEOUT):
            return await loop.run_in_executor(self._pool, lambda: fn(*args, **kwargs))

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
