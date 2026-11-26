"""The Alexa skill: turns voice intents and playback events into AudioPlayer responses."""

from __future__ import annotations

import asyncio
import logging
import time
import weakref
from dataclasses import dataclass
from typing import Any

from echo_tunes import tokens
from echo_tunes.alexa import responses as r
from echo_tunes.history import History
from echo_tunes.metrics import METRICS
from echo_tunes.music.catalog import Catalog, Collection, NotSignedIn, Track
from echo_tunes.music.resolver import AudioResolver
from echo_tunes.player.state import PlayerState
from echo_tunes.player.store import StateStore

log = logging.getLogger(__name__)

MAX_FAILURES_IN_A_ROW = 3

HELP = (
    "You can say: play, followed by a song or artist. Or: play radio for, followed by a song. "
    "If you've signed in, say: play my liked songs, play my supermix, "
    "or play my playlist, followed by its name. "
    "While music plays, say next, previous, pause, shuffle, or ask what's playing."
)
SIGN_IN_FIRST = (
    "To play your own music, sign in to YouTube Music first. Run echo tunes login on your server."
)


@dataclass(frozen=True, slots=True)
class SkillConfig:
    base_url: str
    stream_secret: bytes
    stream_ttl_seconds: int
    radio_length: int
    max_queue: int


class Skill:
    def __init__(
        self,
        cfg: SkillConfig,
        catalog: Catalog,
        resolver: AudioResolver,
        store: StateStore,
        history: History | None = None,
    ) -> None:
        self.cfg = cfg
        self.history = history
        self.catalog = catalog
        self.resolver = resolver
        self.store = store
        # One lock per Echo so its events are handled in order. Weak values: a lock disappears
        # as soon as nothing is waiting on it, so this never grows.
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._background: set[asyncio.Task[None]] = set()

    # --- entry point ------------------------------------------------------------------------
    async def handle(self, envelope: dict[str, Any]) -> r.Response:
        request = envelope.get("request") or {}
        kind = str(request.get("type", ""))
        device = _device_id(envelope)
        async with self._lock_for(device):
            state = self.store.get(device)
            try:
                response = await self._dispatch(kind, request, envelope, state, device)
            finally:
                self.store.put(device, state)
        return response

    async def _dispatch(
        self,
        kind: str,
        request: dict[str, Any],
        envelope: dict[str, Any],
        state: PlayerState,
        device: str,
    ) -> r.Response:
        if kind == "LaunchRequest":
            return r.build(
                "What would you like to play?",
                reprompt="Say play, followed by a song or artist.",
                end_session=False,
            )
        if kind == "IntentRequest":
            return await self._intent(request, envelope, state, device)
        if kind.startswith("AudioPlayer."):
            return await self._audio_event(
                kind.removeprefix("AudioPlayer."), request, state, device
            )
        if kind.startswith("PlaybackController."):
            return await self._button(kind.removeprefix("PlaybackController."), envelope, state)
        if kind == "System.ExceptionEncountered":
            log.warning("Alexa reported an error: %s", (request.get("error") or {}).get("message"))
            return r.empty()
        if kind == "SessionEndedRequest":
            return r.empty()
        log.info("ignoring request type %s", kind)
        return r.empty()

    # --- voice intents ------------------------------------------------------------------------
    async def _intent(
        self, request: dict[str, Any], envelope: dict[str, Any], state: PlayerState, device: str
    ) -> r.Response:
        intent = request.get("intent") or {}
        name = str(intent.get("name", ""))
        query = _slot(intent, "query")
        METRICS.intent(name)

        match name:
            case "PlayIntent" | "PlayRadioIntent":
                if not query:
                    return r.build(
                        "What should I play?", reprompt="Say a song or artist.", end_session=False
                    )
                return await self._start(
                    query, state, device, radio_intro=name == "PlayRadioIntent"
                )
            case "PlayLikedIntent" | "PlayPlaylistIntent" | "PlayMixIntent":
                return await self._start_collection(name, intent, state)
            case "LikeIntent":
                return await self._like(state)
            case "WhatsPlayingIntent":
                cur = state.current
                return r.build(f"This is {cur.spoken}." if cur else "Nothing is playing.")
            case "AMAZON.PauseIntent" | "AMAZON.StopIntent" | "AMAZON.CancelIntent":
                return r.build(directives=[r.stop()])
            case "AMAZON.ResumeIntent":
                return self._resume(envelope, state, speak=True)
            case "AMAZON.NextIntent":
                return await self._skip(state, forward=True, speak=True)
            case "AMAZON.PreviousIntent":
                return await self._skip(state, forward=False, speak=True)
            case "AMAZON.StartOverIntent" | "AMAZON.RepeatIntent":
                if not state.current:
                    return r.build("Nothing is playing.")
                return r.build(directives=[self._play(state, state.index)])
            case "AMAZON.ShuffleOnIntent" | "AMAZON.ShuffleOffIntent":
                on = name == "AMAZON.ShuffleOnIntent"
                state.set_shuffle(on)
                return r.build(
                    f"Shuffle {'on' if on else 'off'}.", directives=self._requeue_next(state)
                )
            case "AMAZON.LoopOnIntent" | "AMAZON.LoopOffIntent":
                state.loop = name == "AMAZON.LoopOnIntent"
                return r.build(
                    f"Loop {'on' if state.loop else 'off'}.", directives=self._requeue_next(state)
                )
            case "AMAZON.HelpIntent":
                return r.build(HELP, reprompt="What would you like to play?", end_session=False)
            case "AMAZON.FallbackIntent":
                return r.build(
                    "Sorry, I didn't get that. Say play, followed by a song or artist.",
                    reprompt="What would you like to play?",
                    end_session=False,
                )
            case _:
                return r.build()

    async def _start(
        self, query: str, state: PlayerState, device: str, *, radio_intro: bool
    ) -> r.Response:
        try:
            track = await self.catalog.search_song(query)
        except Exception:
            log.exception("search failed")
            METRICS.youtube_errors.inc()
            return r.build("Sorry, I couldn't reach YouTube Music. Please try again.")
        if track is None:
            return r.build(f"Sorry, I couldn't find {query}.")
        self.resolver.warm(track.video_id)  # start fetching the audio link right away
        state.replace([track], self.cfg.max_queue)
        state.failures = 0
        state.source = f'{"Radio for" if radio_intro else "Asked for"} "{query}"'
        state.source_kind = "radio" if radio_intro else "ask"
        # Answer Alexa now (it allows ~8 s); the radio that follows is fetched afterwards.
        self._in_background(self._fill_radio(device, state.rev, track))
        intro = "Starting radio based on" if radio_intro else "Playing"
        return r.build(f"{intro} {track.spoken}.", directives=[self._play(state, 0)])

    async def _fill_radio(self, device: str, rev: int, seed: Track) -> None:
        try:
            radio = await self.catalog.radio(seed.video_id, self.cfg.radio_length)
        except Exception as exc:
            log.warning("radio for %s failed: %s", seed.video_id, exc)
            return
        async with self._lock_for(device):
            state = self.store.get(device)
            if state.rev != rev:  # something else was asked for meanwhile
                return
            state.extend(radio, self.cfg.max_queue)
            self.store.put(device, state)
            self._warm_next(state)

    def _lock_for(self, device: str) -> asyncio.Lock:
        lock = self._locks.get(device)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[device] = lock
        return lock

    async def wait_background(self) -> None:
        """Wait for background work (tests use this)."""
        while self._background:
            await asyncio.gather(*list(self._background), return_exceptions=True)

    async def _start_collection(
        self, name: str, intent: dict[str, Any], state: PlayerState
    ) -> r.Response:
        """Play liked songs, a playlist or a mix from the signed-in account."""
        wanted = _slot(intent, "playlist") or _slot(intent, "mix", resolved=True)
        try:
            coll: Collection | None
            if name == "PlayLikedIntent":
                coll = await self.catalog.liked_songs()
            elif name == "PlayPlaylistIntent":
                if not wanted:
                    return r.build(
                        "Which playlist?", reprompt="Say the playlist's name.", end_session=False
                    )
                coll = await self.catalog.playlist(wanted)
            else:
                coll = await self.catalog.mix(wanted or "supermix")
        except NotSignedIn:
            return r.build(SIGN_IN_FIRST)
        except Exception:
            log.exception("loading %s failed", name)
            METRICS.youtube_errors.inc()
            return r.build("Sorry, I couldn't reach YouTube Music. Please try again.")
        if coll is None:
            what = f"a playlist called {wanted}" if name == "PlayPlaylistIntent" else "that mix"
            return r.build(f"Sorry, I couldn't find {what} in your library.")
        if not coll.tracks:
            return r.build(f"{coll.title} has no songs I can play.")
        self.resolver.warm(coll.tracks[0].video_id)
        state.replace(coll.tracks, self.cfg.max_queue)
        state.failures = 0
        state.source = {
            "PlayLikedIntent": "Liked songs",
            "PlayPlaylistIntent": f"Playlist: {coll.title}",
        }.get(name, f"Mix: {coll.title}")
        state.source_kind = "library"
        return r.build(f"Playing {coll.title}.", directives=[self._play(state, 0)])

    async def _like(self, state: PlayerState) -> r.Response:
        cur = state.current
        if cur is None:
            return r.build("Nothing is playing.")
        try:
            await self.catalog.like(cur.video_id)
        except NotSignedIn:
            return r.build(SIGN_IN_FIRST)
        except Exception:
            log.exception("like failed")
            return r.build("Sorry, I couldn't reach YouTube Music.")
        return r.build(f"Added {cur.title} to your liked songs.")

    def _resume(self, envelope: dict[str, Any], state: PlayerState, *, speak: bool) -> r.Response:
        if not state.current:
            return (
                r.build("There's nothing to resume. Say play, followed by a song.")
                if speak
                else r.empty()
            )
        audio = (envelope.get("context") or {}).get("AudioPlayer") or {}
        index, offset = state.index, state.offset_ms
        if state.finished:
            # The song already played to its end: go on to the next one, or start it over.
            nxt = state.next_index()
            index, offset = (nxt if nxt is not None else state.index), 0
        elif state.index_from_token(audio.get("token")) == state.index:
            offset = int(audio.get("offsetInMilliseconds") or offset)
        directive = self._play(state, index, offset_ms=offset)
        return r.build(directives=[directive]) if speak else r.only(directive)

    async def _skip(self, state: PlayerState, *, forward: bool, speak: bool) -> r.Response:
        if not state.current:
            return r.build("Nothing is playing.") if speak else r.empty()
        idx = state.next_index() if forward else state.previous_index()
        if idx is None and forward:
            await self._top_up(state)
            idx = state.next_index()
        if idx is None:
            msg = "That's the end of the queue." if forward else "This is the first song."
            return r.build(msg) if speak else r.empty()
        directive = self._play(state, idx)
        if speak:
            return r.build(directives=[directive])
        return r.only(directive)

    def _requeue_next(self, state: PlayerState) -> list[dict[str, Any]]:
        """Swap the song the Echo has queued next for the new next song.

        The Echo usually asked for its next song (PlaybackNearlyFinished, sent once per song)
        long before the user says "shuffle", so a bare ClearQueue would leave nothing to play
        when the current song ends. REPLACE_ENQUEUED swaps it without touching the current one.
        """
        if not state.current:
            return []
        nxt = state.next_index()
        if nxt is None:
            return [r.clear_enqueued()]
        return [self._play(state, nxt, behavior="REPLACE_ENQUEUED")]

    # --- playback events (no speech allowed) --------------------------------------------------
    async def _audio_event(
        self, event: str, request: dict[str, Any], state: PlayerState, device: str
    ) -> r.Response:
        token = request.get("token")
        idx = state.index_from_token(token)
        offset = int(request.get("offsetInMilliseconds") or 0)
        track = state.tracks[idx] if idx is not None else None
        match event:
            case "PlaybackStarted":
                jump = self._pending_jump(state, track)
                if jump is not None:
                    return r.only(jump)
                if idx is not None and track is not None:
                    state.index, state.offset_ms, state.failures = idx, 0, 0
                    state.finished = False
                    self._now(state, playing=True, position_ms=offset)
                    # A start part-way through the song is a resume, not a new play.
                    resumed = offset > 0 and bool(
                        self.history and self.history.resumed(device, track.video_id)
                    )
                    if not resumed:
                        METRICS.songs_started.inc()
                        if self.history:
                            self.history.started(device, track, state.source_of(idx))
                        self._in_background(self.catalog.played(track.video_id))
                    self._warm_next(state)
            case "PlaybackStopped":
                if idx is not None and track is not None:
                    state.index = idx
                    state.offset_ms = offset
                    self._now(state, playing=False, position_ms=offset)
                    if self.history:
                        self.history.ended(device, track.video_id, "stopped", offset)
            case "PlaybackFinished":
                if idx is not None and track is not None:
                    self._now(state, playing=False, position_ms=offset)
                    if idx == state.index:
                        state.finished, state.offset_ms = True, 0
                    if self.history:
                        full = track.duration * 1000 if track.duration else None
                        self.history.ended(device, track.video_id, "finished", full or offset)
            case "PlaybackNearlyFinished":
                if idx is None:
                    return r.empty()
                state.index = idx
                nxt = state.next_index()
                if nxt is None:
                    await self._top_up(state)
                    nxt = state.next_index()
                if nxt is not None:
                    directive = self._play(state, nxt, behavior="ENQUEUE", expected_previous=token)
                    return r.only(directive)
            case "PlaybackFailed":
                err = request.get("error") or {}
                log.warning(
                    "Echo could not play %s: %s", token, err.get("message") or err.get("type")
                )
                METRICS.playback_failures.inc()
                if idx is None or track is None:
                    return r.empty()
                self._now(state, playing=False, position_ms=offset)
                if self.history:
                    self.history.ended(device, track.video_id, "failed", offset)
                self.resolver.invalidate(track.video_id)
                state.failures += 1
                if state.failures >= MAX_FAILURES_IN_A_ROW:
                    log.warning("%d songs failed in a row; stopping", state.failures)
                    return r.empty()
                playing = request.get("currentPlaybackState") or {}
                still_playing = (
                    playing.get("playerActivity") == "PLAYING"
                    and playing.get("token")
                    and playing.get("token") != token
                )
                after = self._index_after(state, idx)
                if after is None:
                    await self._top_up(state)
                    after = self._index_after(state, idx)
                if after is None:
                    return r.empty()
                if still_playing:
                    # The song queued *next* failed while another still plays: queue the one
                    # after it instead, without cutting off what's playing.
                    return r.only(self._play(state, after, behavior="REPLACE_ENQUEUED"))
                jump = self._pending_jump(state, None)  # e.g. "skip now" from the dashboard
                if jump is not None:
                    return r.only(jump)
                state.index = idx
                return r.only(self._play(state, after))
        return r.empty()

    async def _button(
        self, command: str, envelope: dict[str, Any], state: PlayerState
    ) -> r.Response:
        match command:
            case "PlayCommandIssued":
                return self._resume(envelope, state, speak=False)
            case "PauseCommandIssued":
                return r.only(r.stop())
            case "NextCommandIssued":
                return await self._skip(state, forward=True, speak=False)
            case "PreviousCommandIssued":
                return await self._skip(state, forward=False, speak=False)
        return r.empty()

    # --- from the dashboard's player ----------------------------------------------------------
    async def dashboard_queue(
        self, device: str, tracks: list[Track], mode: str, source: str
    ) -> dict[str, Any]:
        """Queue songs on an Echo: ``next``, ``queue`` (at the end) or ``now``.

        Alexa only lets a skill change playback in reply to the Echo, so nothing changes this
        instant: the songs play when the current one ends, and ``now`` jumps to the first one
        at the Echo's next playback event (if it had already lined up another song).
        """
        if mode not in ("next", "queue", "now"):
            raise ValueError("mode must be next, queue or now")
        async with self._lock_for(device):
            state = self.store.get(device)
            if state.current is None:
                raise LookupError("Start something on this Echo by voice first.")
            placed = state.insert(tracks, at_end=mode == "queue", max_len=self.cfg.max_queue)
            first = next(iter(t for t in tracks if state.position_of(t.video_id) is not None), None)
            if mode == "now" and first is not None and first != state.current:
                state.pending = first.video_id
            if placed and mode != "queue":
                state.source = source
            self.store.put(device, state)
            self._warm_next(state)
        note = "Plays after the current song." if mode != "queue" else "Added to the end."
        return {"placed": placed, "note": note}

    async def dashboard_skip(self, device: str) -> str | None:
        """Mark the next song to jump to; returns the current song's ID (whose stream the
        caller cuts, so the Echo moves on)."""
        async with self._lock_for(device):
            state = self.store.get(device)
            cur = state.current
            if cur is None:
                return None
            nxt = state.next_index()
            if nxt is None:
                await self._top_up(state)
                nxt = state.next_index()
            if nxt is not None and not state.pending:
                state.pending = state.tracks[nxt].video_id
            self.store.put(device, state)
            return cur.video_id

    def _pending_jump(self, state: PlayerState, started: Track | None) -> dict[str, Any] | None:
        """A song is starting but the dashboard asked for another one: switch to it now."""
        if not state.pending:
            return None
        if started is not None and started.video_id == state.pending:
            state.pending = ""
            return None
        j = state.position_of(state.pending)
        state.pending = ""
        if j is None:
            return None
        return self._play(state, j)

    # --- helpers --------------------------------------------------------------------------------
    def _play(
        self,
        state: PlayerState,
        index: int,
        *,
        behavior: str = "REPLACE_ALL",
        offset_ms: int = 0,
        expected_previous: str | None = None,
    ) -> dict[str, Any]:
        track = state.tracks[index]
        if behavior == "REPLACE_ALL":
            state.index = index
        self.resolver.warm(track.video_id)
        return r.play(
            track,
            url=self.stream_url(track.video_id),
            token=state.token(index),
            behavior=behavior,
            offset_ms=offset_ms,
            expected_previous=expected_previous,
        )

    def stream_url(self, video_id: str, ttl_seconds: int | None = None) -> str:
        t = tokens.make(
            self.cfg.stream_secret, video_id, ttl_seconds or self.cfg.stream_ttl_seconds
        )
        return f"{self.cfg.base_url}/stream/{t}.m4a"

    @staticmethod
    def _now(state: PlayerState, *, playing: bool, position_ms: int) -> None:
        state.playing = playing
        state.position_ms = position_ms
        state.since = time.time()

    def _in_background(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    @staticmethod
    def _index_after(state: PlayerState, idx: int) -> int | None:
        if idx + 1 < len(state.tracks):
            return idx + 1
        return 0 if state.loop and len(state.tracks) > 1 else None

    def _warm_next(self, state: PlayerState) -> None:
        nxt = state.next_index()
        if nxt is not None:
            self.resolver.warm(state.tracks[nxt].video_id)

    async def _top_up(self, state: PlayerState) -> None:
        """Queue ran out: keep the music going with radio based on the current song."""
        if state.loop or not state.current:
            return
        try:
            more = await self.catalog.radio(state.current.video_id, self.cfg.radio_length)
        except Exception as exc:
            log.warning("could not extend the queue: %s", exc)
            return
        state.extend(more, self.cfg.max_queue)


def _device_id(envelope: dict[str, Any]) -> str:
    system = (envelope.get("context") or {}).get("System") or {}
    return str((system.get("device") or {}).get("deviceId") or "unknown")


def _slot(intent: dict[str, Any], name: str, *, resolved: bool = False) -> str:
    """A slot's spoken words, or with ``resolved`` the value its synonym maps to.

    E.g. "second mix" is a synonym of "mix 2" in the voice model; only the resolved value
    matches the mix's real title.
    """
    slot = (intent.get("slots") or {}).get(name) or {}
    if resolved:
        for auth in (slot.get("resolutions") or {}).get("resolutionsPerAuthority") or []:
            if (auth.get("status") or {}).get("code") != "ER_SUCCESS_MATCH":
                continue
            for v in auth.get("values") or []:
                value = ((v or {}).get("value") or {}).get("name")
                if value:
                    return str(value).strip()
    return str(slot.get("value") or "").strip()
