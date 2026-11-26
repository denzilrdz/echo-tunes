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
    rev: int = 0  # bumped whenever the queue is replaced, so stale Alexa tokens are ignored
    offset_ms: int = 0  # where playback stopped, for "resume"
    failures: int = 0  # songs that failed to play in a row

    # --- tokens -------------------------------------------------------------------------
    # Alexa hands this back in every playback event, so it identifies queue + position.
    def token(self, index: int | None = None) -> str:
        i = self.index if index is None else index
        return f"{self.rev}:{i}:{self.tracks[i].video_id}"

    def index_from_token(self, token: str | None) -> int | None:
        if not token:
            return None
        parts = token.split(":")
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            return None
        rev, i = int(parts[0]), int(parts[1])
        if rev != self.rev or i >= len(self.tracks) or self.tracks[i].video_id != parts[2]:
            return None
        return i

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
        self.rev += 1
        if self.shuffle:
            self._shuffle_rest()

    def extend(self, tracks: list[Track], max_len: int) -> int:
        """Append unseen tracks; drop played ones from the front if over max_len."""
        known = {t.video_id for t in self.tracks}
        added = [t for t in tracks if t.video_id not in known]
        self.tracks.extend(added)
        overflow = len(self.tracks) - max_len
        if overflow > 0:
            drop = min(overflow, self.index)  # never drop the current or upcoming songs
            if drop:
                self.tracks = self.tracks[drop:]
                self.index -= drop
                self.rev += 1
            self.tracks = self.tracks[:max_len]
        return len(added)

    def next_index(self) -> int | None:
        if self.index + 1 < len(self.tracks):
            return self.index + 1
        return 0 if self.loop and self.tracks else None

    def previous_index(self) -> int | None:
        if self.index > 0:
            return self.index - 1
        return len(self.tracks) - 1 if self.loop and self.tracks else None

    def set_shuffle(self, on: bool) -> None:
        self.shuffle = on
        if on:
            self._shuffle_rest()

    def _shuffle_rest(self) -> None:
        rest = self.tracks[self.index + 1 :]
        random.shuffle(rest)
        self.tracks[self.index + 1 :] = rest
        self.rev += 1

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
        )
