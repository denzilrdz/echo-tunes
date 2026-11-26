"""What each Echo is playing: its queue, position and play modes."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from echo_tunes.music.catalog import Track


@dataclass(slots=True)
class PlayerState:
    tracks: list[Track] = field(default_factory=list)
    index: int = 0
    shuffle: bool = False
    loop: bool = False
    # Bumped only when the queue is *replaced* (a new request), so tokens from an old queue are
    # ignored. Reordering (shuffle) or trimming keeps it: tokens are matched by song ID.
    rev: int = 0
    offset_ms: int = 0  # where playback stopped, for "resume"
    failures: int = 0  # songs that failed to play in a row
    # For the dashboard and history: where the queue came from and what the Echo is doing.
    source: str = ""  # e.g. 'Asked for "mercedes by clayjars"', 'Playlist: Road Trip'
    source_kind: str = ""  # ask | radio | library
    playing: bool = False
    position_ms: int = 0  # playback position at `since`
    since: float = 0.0  # wall-clock time of the last start/stop event
    finished: bool = False  # the current song played to its end (resume starts over/next)
    plays: int = 0  # bumped for every Play directive, so no two streams share a token
    unshuffled: list[str] = field(default_factory=list)  # queue order before shuffle (IDs)
    # A song chosen on the dashboard to play as soon as the Echo lets us (its next event).
    # Cleared by anything newer: a new queue, or a voice/button command that plays a song.
    pending: str = ""
    # The song the Echo has lined up after the current one (we answered PlaybackNearlyFinished
    # with ENQUEUE, or sent REPLACE_ENQUEUED); "" when it has nothing queued. "Play next" goes
    # after it, and a mode change only swaps it when there is one.
    enqueued: str = ""

    def source_of(self, index: int) -> str:
        """Why this song is playing, for the history."""
        if self.source_kind in ("ask", "radio") and index > 0 and self.tracks:
            return f"Radio after {self.tracks[0].title}"
        return self.source

    # --- tokens -------------------------------------------------------------------------
    # Alexa hands this back in every playback event, so it identifies queue + position.
    def token(self, index: int | None = None) -> str:
        """A new token for playing ``index``: rev, position, song and a play counter.

        The counter keeps tokens unique when the same song is queued right after itself
        (loop with one song); Alexa rejects an ENQUEUE whose token equals the playing one.
        """
        i = self.index if index is None else index
        self.plays += 1
        return f"{self.rev}:{i}:{self.tracks[i].video_id}:{self.plays}"

    def index_from_token(self, token: str | None) -> int | None:
        if not token:
            return None
        parts = token.split(":")
        if len(parts) == 4 and parts[3].isdigit():
            parts = parts[:3]
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            return None
        rev, i, video = int(parts[0]), int(parts[1]), parts[2]
        if rev != self.rev:
            return None
        if i < len(self.tracks) and self.tracks[i].video_id == video:
            return i
        # Shuffled or trimmed since: find the song by ID (songs in a queue are unique).
        return next((j for j, t in enumerate(self.tracks) if t.video_id == video), None)

    # --- queue --------------------------------------------------------------------------
    @property
    def current(self) -> Track | None:
        return self.tracks[self.index] if 0 <= self.index < len(self.tracks) else None

    def replace(self, tracks: list[Track], max_len: int) -> None:
        first: dict[str, Track] = {}
        for t in tracks:
            first.setdefault(t.video_id, t)  # keep the first copy of each song, in order
        self.tracks = list(first.values())[:max_len]
        self.index = 0
        self.offset_ms = 0
        self.finished = False
        self.rev += 1
        self.pending = ""  # a pick from the old queue must not hijack the new one
        self.enqueued = ""  # the reply that plays this queue replaces the Echo's whole queue
        self.unshuffled = []
        if self.shuffle:
            # Remember the order even for one song: radio added later is shuffled in.
            self.unshuffled = [t.video_id for t in self.tracks]
            # A new playlist starts on a random song too, not always its first.
            random.shuffle(self.tracks)

    def _upcoming_from(self) -> int:
        """Where songs that haven't been lined up yet start: after the current song, or after
        the one the Echo has already queued (it plays that next whatever we do)."""
        j = self.position_of(self.enqueued) if self.enqueued else None
        return j + 1 if j is not None and j > self.index else self.index + 1

    def extend(self, tracks: list[Track], max_len: int) -> int:
        """Append unseen tracks; drop played ones from the front if over max_len."""
        known = {t.video_id for t in self.tracks}
        added: list[Track] = []
        for t in tracks:
            if t.video_id not in known:
                known.add(t.video_id)
                added.append(t)
        if self.shuffle and added:
            # Shuffle on: new songs (e.g. radio) are mixed into what's still to come.
            start = self._upcoming_from()
            rest = self.tracks[start:] + added
            random.shuffle(rest)
            self.tracks[start:] = rest
        else:
            self.tracks.extend(added)
        if self.shuffle:
            self.unshuffled.extend(t.video_id for t in added)
        overflow = len(self.tracks) - max_len
        if overflow > 0:
            drop = min(overflow, self.index)  # never drop the current or upcoming songs
            if drop:
                self.tracks = self.tracks[drop:]
                self.index -= drop
            self.tracks = self.tracks[:max_len]
        if self.unshuffled:
            kept = {t.video_id for t in self.tracks}
            self.unshuffled = [v for v in self.unshuffled if v in kept]
        return len(added)

    def insert(
        self, tracks: list[Track], *, at_end: bool, max_len: int, after_enqueued: bool = False
    ) -> int:
        """Put songs right after the current one (or at the end), moving them if queued already.

        With ``after_enqueued``, they go after the song the Echo has already lined up instead
        (it plays that one next whatever we do, so a pick placed before it would be skipped).
        The current song stays where it is and tokens stay valid (they're matched by song).
        Returns how many of the songs are in the queue afterwards.
        """
        cur = self.current
        keep = {cur.video_id} if cur else set()
        anchor = self.index
        if after_enqueued and cur:
            anchor = self._upcoming_from() - 1
            keep.add(self.tracks[anchor].video_id)
        incoming = [t for t in dict((t.video_id, t) for t in tracks).values()]
        incoming = [t for t in incoming if t.video_id not in keep]
        ids = {t.video_id for t in incoming}
        before = [t for t in self.tracks[: anchor + 1] if t.video_id not in ids]
        after = [t for t in self.tracks[anchor + 1 :] if t.video_id not in ids]
        self.tracks = before + after + incoming if at_end else before + incoming + after
        if cur:
            self.index = next(i for i, t in enumerate(self.tracks) if t.video_id == cur.video_id)
        else:
            self.index = 0
        overflow = len(self.tracks) - max_len
        if overflow > 0:
            drop = min(overflow, self.index)
            self.tracks = self.tracks[drop:][:max_len]
            self.index -= drop
        kept = {t.video_id for t in self.tracks}
        if self.shuffle:
            # Keep the order to go back to when shuffle is turned off: the user's original
            # order, with the picks after the current song (or at the end).
            order = [v for v in self.unshuffled if v not in ids]
            new = [t.video_id for t in incoming]
            at = len(order)
            if not at_end and cur and cur.video_id in order:
                at = order.index(cur.video_id) + 1
            order[at:at] = new
            self.unshuffled = [v for v in order if v in kept]
            saved = set(self.unshuffled)
            self.unshuffled += [t.video_id for t in self.tracks if t.video_id not in saved]
        return sum(1 for t in incoming if t.video_id in kept)

    def position_of(self, video_id: str) -> int | None:
        return next((i for i, t in enumerate(self.tracks) if t.video_id == video_id), None)

    def next_index(self) -> int | None:
        if self.index + 1 < len(self.tracks):
            return self.index + 1
        return 0 if self.loop and self.tracks else None

    def previous_index(self) -> int | None:
        if self.index > 0:
            return self.index - 1
        return len(self.tracks) - 1 if self.loop and self.tracks else None

    def set_shuffle(self, on: bool) -> None:
        if on and not self.shuffle:
            self.unshuffled = [t.video_id for t in self.tracks]
        self.shuffle = on
        if on:
            rest = self.tracks[self.index + 1 :]
            random.shuffle(rest)
            self.tracks[self.index + 1 :] = rest
        elif self.unshuffled:
            # Back to the original order for the songs after the current one.
            rank = {v: n for n, v in enumerate(self.unshuffled)}
            rest = sorted(
                self.tracks[self.index + 1 :], key=lambda t: rank.get(t.video_id, 1 << 30)
            )
            self.tracks[self.index + 1 :] = rest
            self.unshuffled = []

    # --- storage ------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "tracks": [t.to_dict() for t in self.tracks],
            "index": self.index,
            "shuffle": self.shuffle,
            "loop": self.loop,
            "rev": self.rev,
            "offset_ms": self.offset_ms,
            "failures": self.failures,
            "source": self.source,
            "source_kind": self.source_kind,
            "playing": self.playing,
            "position_ms": self.position_ms,
            "since": self.since,
            "finished": self.finished,
            "plays": self.plays,
            "unshuffled": self.unshuffled,
            "pending": self.pending,
            "enqueued": self.enqueued,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlayerState:
        return cls(
            tracks=[Track.from_dict(t) for t in d.get("tracks", [])],
            index=int(d.get("index", 0)),
            shuffle=bool(d.get("shuffle", False)),
            loop=bool(d.get("loop", False)),
            rev=int(d.get("rev", 0)),
            offset_ms=int(d.get("offset_ms", 0)),
            failures=int(d.get("failures", 0)),
            source=str(d.get("source", "")),
            source_kind=str(d.get("source_kind", "")),
            playing=bool(d.get("playing", False)),
            position_ms=int(d.get("position_ms", 0)),
            since=float(d.get("since", 0.0)),
            finished=bool(d.get("finished", False)),
            plays=int(d.get("plays", 0)),
            unshuffled=[str(v) for v in d.get("unshuffled", [])],
            pending=str(d.get("pending", "")),
            enqueued=str(d.get("enqueued", "")),
        )
