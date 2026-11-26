"""A Hypothesis state machine over PlayerState: random sequences of replace, extend, shuffle,
loop, next/previous and token round trips must keep the queue consistent."""

from __future__ import annotations

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from echo_tunes.player.state import PlayerState

from .conftest import song

MAX = 30
songs = st.lists(st.integers(0, 60).map(song), min_size=1, max_size=40)


class Queue(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.s = PlayerState()
        self.s.replace([song(0)], MAX)
        self.tokens: list[tuple[str, str]] = []  # (token, video ID) of the current queue

    @rule(tracks=songs, shuffle=st.booleans())
    def replace(self, tracks: list, shuffle: bool) -> None:  # type: ignore[type-arg]
        self.s.shuffle = shuffle
        self.s.replace(tracks, MAX)
        self.tokens = []
        unique = list(dict.fromkeys(t.video_id for t in tracks))[:MAX]
        assert sorted(t.video_id for t in self.s.tracks) == sorted(unique)
        if not shuffle:
            assert [t.video_id for t in self.s.tracks] == unique

    @rule(tracks=songs)
    def extend(self, tracks: list) -> None:  # type: ignore[type-arg]
        current = self.s.current
        self.s.extend(tracks, MAX)
        assert self.s.current == current  # never moves or drops the playing song

    @rule(on=st.booleans())
    def shuffle(self, on: bool) -> None:
        current, ids = self.s.current, sorted(t.video_id for t in self.s.tracks)
        self.s.set_shuffle(on)
        assert self.s.current == current
        assert sorted(t.video_id for t in self.s.tracks) == ids

    @rule(on=st.booleans())
    def loop(self, on: bool) -> None:
        self.s.loop = on

    @rule()
    def next(self) -> None:
        nxt = self.s.next_index()
        if nxt is not None:
            self.s.index = nxt

    @rule()
    def previous(self) -> None:
        prev = self.s.previous_index()
        if prev is not None:
            self.s.index = prev

    @rule()
    def take_token(self) -> None:
        if self.s.current:
            self.tokens.append((self.s.token(), self.s.current.video_id))

    @invariant()
    def consistent(self) -> None:
        s = self.s
        ids = [t.video_id for t in s.tracks]
        assert len(ids) == len(set(ids)), "songs in a queue are unique"
        assert len(ids) <= MAX
        assert 0 <= s.index < len(ids)
        for token, video in self.tokens:
            # A token from this queue still finds its song, wherever it moved, while it's queued.
            i = s.index_from_token(token)
            if video in ids:
                assert i is not None and s.tracks[i].video_id == video
            else:
                assert i is None
        if not s.shuffle:
            assert not s.unshuffled, "the saved order is only kept while shuffle is on"
        n = s.next_index()
        assert n is None or 0 <= n < len(ids)


TestQueue = Queue.TestCase
TestQueue.settings = settings(max_examples=150, stateful_step_count=40, deadline=None)
