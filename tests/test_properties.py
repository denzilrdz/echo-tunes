"""Property-based tests (fuzzing) for the code that handles untrusted input.

Hypothesis generates hundreds of random and adversarial inputs per test and checks the
invariants always hold: parsers never crash with an unexpected error, and nothing invalid is
ever accepted.
"""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from echo_tunes import tokens
from echo_tunes.alexa.verify import RequestRejected, check_cert_url
from echo_tunes.music.catalog import best_match, normalise
from echo_tunes.player.state import PlayerState
from echo_tunes.stream import StreamError, parse_range

from .conftest import song

SECRET = b"k" * 32
VIDEO = st.text(alphabet=string.ascii_letters + string.digits + "-_", min_size=11, max_size=11)
settings.register_profile("ci", max_examples=300, deadline=None)
settings.load_profile("ci")


# --- stream links ------------------------------------------------------------------------------
@given(VIDEO, st.integers(min_value=1, max_value=10**6))
def test_tokens_round_trip(video: str, ttl: int) -> None:
    assert tokens.check(SECRET, tokens.make(SECRET, video, ttl, now=0), now=0) == video


@given(st.text(max_size=200))
def test_random_tokens_are_rejected_cleanly(text: str) -> None:
    try:
        tokens.check(SECRET, text)
    except tokens.BadToken:
        return
    raise AssertionError(f"accepted a forged token: {text!r}")


@given(VIDEO, st.integers(0, 60), st.text(alphabet=string.printable, min_size=1, max_size=3))
def test_an_edited_link_never_points_elsewhere(video: str, pos: int, junk: str) -> None:
    """Editing a link must not yield a different song or a later expiry. (The signature's last
    base64 character has spare bits, so a few edits decode to the same bytes: harmless.)"""
    good = tokens.make(SECRET, video, 3600, now=0)
    i = pos % len(good)
    forged = good[:i] + junk + good[i + 1 :]
    try:
        got = tokens.check(SECRET, forged, now=0)
    except tokens.BadToken:
        return
    assert got == video
    assert forged.split(".")[:2] == good.split(".")[:2]


# --- byte ranges ---------------------------------------------------------------------------------
@given(st.text(max_size=40), st.integers(min_value=1, max_value=10**9))
def test_range_parser_never_crashes_and_stays_in_bounds(header: str, total: int) -> None:
    try:
        r = parse_range(header, total)
    except StreamError as exc:
        assert exc.status == 416
        return
    assert 0 <= r.start <= r.end < total
    assert r.length == r.end - r.start + 1


@given(st.integers(0, 10**6), st.integers(0, 10**6), st.integers(1, 10**6))
def test_valid_ranges_round_trip(a: int, b: int, total: int) -> None:
    start, end = sorted((a, b))
    if start >= total:
        return
    r = parse_range(f"bytes={start}-{end}", total)
    assert (r.start, r.end) == (start, min(end, total - 1))


# --- Amazon certificate URLs ---------------------------------------------------------------------
@given(st.text(max_size=120))
def test_cert_url_check_never_crashes(url: str) -> None:
    try:
        clean = check_cert_url(url)
    except RequestRejected:
        return
    assert clean.startswith("https://s3.amazonaws.com/echo.api/")


@given(st.text(alphabet=string.ascii_letters + string.digits + "./-_%?#@:", max_size=60))
def test_only_amazon_paths_pass(path: str) -> None:
    url = "https://s3.amazonaws.com/" + path
    try:
        clean = check_cert_url(url)
    except RequestRejected:
        return
    assert clean.startswith("https://s3.amazonaws.com/echo.api/")
    assert "?" not in clean and "#" not in clean and "@" not in clean


# --- Alexa playback tokens and the queue ----------------------------------------------------------
@given(st.text(max_size=60))
def test_playback_tokens_from_alexa_never_crash(token: str) -> None:
    s = PlayerState()
    s.replace([song(i) for i in range(5)], max_len=10)
    idx = s.index_from_token(token)
    assert idx is None or 0 <= idx < len(s.tracks)


@given(st.lists(st.integers(0, 30), max_size=80), st.integers(5, 40))
def test_queue_stays_bounded_and_unique(ids: list[int], max_len: int) -> None:
    s = PlayerState()
    s.replace([song(i) for i in ids], max_len=max_len)
    s.extend([song(i) for i in reversed(ids)], max_len=max_len)
    assert len(s.tracks) <= max_len
    assert len({t.video_id for t in s.tracks}) == len(s.tracks)


# --- spoken playlist names ---------------------------------------------------------------------
@given(st.text(max_size=40), st.lists(st.text(max_size=30), max_size=15))
def test_name_matching_never_crashes(said: str, names: list[str]) -> None:
    i = best_match(said, names)
    assert i is None or 0 <= i < len(names)
    assert normalise(said) == normalise(normalise(said))
