from __future__ import annotations

import pytest

from echo_tunes import tokens
from echo_tunes.cache import BoundedTTLCache
from echo_tunes.player.state import PlayerState
from echo_tunes.player.store import StateStore

from .conftest import SECRET, song


# --- tokens -------------------------------------------------------------------------------------
def test_token_round_trip() -> None:
    t = tokens.make(SECRET, "dQw4w9WgXcQ", 60, now=1000)
    assert tokens.check(SECRET, t, now=1030) == "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.replace("dQw4w9WgXcQ", "aaaaaaaaaaa"),  # different video
        lambda t: t[:-2] + ("AA" if not t.endswith("AA") else "BB"),  # forged signature
        lambda t: t.replace(".1060.", ".9999999999."),  # extended expiry
        lambda t: "garbage",
        lambda t: t + ".extra",
    ],
)
def test_token_tampering_rejected(mutate) -> None:  # type: ignore[no-untyped-def]
    t = tokens.make(SECRET, "dQw4w9WgXcQ", 60, now=1000)
    with pytest.raises(tokens.BadToken):
        tokens.check(SECRET, mutate(t), now=1030)


@pytest.mark.parametrize("expiry", ["²³", "٣٣٣", "1e9", " 99", "-5"])
def test_token_expiry_must_be_ascii_digits(expiry: str) -> None:
    with pytest.raises(tokens.BadToken):
        tokens.check(SECRET, f"dQw4w9WgXcQ.{expiry}.AAAAAAAAAAAAAAAAAAAAAA", now=0)


def test_token_expires_and_needs_right_key() -> None:
    t = tokens.make(SECRET, "dQw4w9WgXcQ", 60, now=1000)
    with pytest.raises(tokens.BadToken, match="expired"):
        tokens.check(SECRET, t, now=2000)
    with pytest.raises(tokens.BadToken):
        tokens.check(b"other" * 8, t, now=1030)


def test_token_rejects_non_video_ids() -> None:
    with pytest.raises(ValueError):
        tokens.make(SECRET, "../etc/passwd", 60)


# --- cache --------------------------------------------------------------------------------------
def test_cache_evicts_least_recently_used() -> None:
    c: BoundedTTLCache[int, int] = BoundedTTLCache(3, ttl=100)
    for i in range(3):
        c.set(i, i)
    c.get(0)  # 0 becomes most recent
    c.set(3, 3)
    assert 1 not in c and 0 in c and len(c) == 3


def test_cache_expires_entries() -> None:
    now = [0.0]
    c: BoundedTTLCache[str, str] = BoundedTTLCache(10, ttl=5, clock=lambda: now[0])
    c.set("a", "x")
    c.set("b", "y", ttl=50)
    now[0] = 10
    assert c.get("a") is None and c.get("b") == "y"


# --- player state -------------------------------------------------------------------------------
def test_state_tokens_and_navigation() -> None:
    s = PlayerState()
    s.replace([song(1), song(2), song(1), song(3)], max_len=10)
    assert [t.video_id for t in s.tracks] == ["vid00000001", "vid00000002", "vid00000003"]
    tok = s.token(1)
    assert s.index_from_token(tok) == 1
    assert s.next_index() == 1 and s.previous_index() is None
    s.replace([song(4)], max_len=10)
    assert s.index_from_token(tok) is None  # old queue
    s.loop = True
    assert s.next_index() == 0


def test_state_extend_is_capped_and_keeps_upcoming() -> None:
    s = PlayerState()
    s.replace([song(i) for i in range(10)], max_len=12)
    s.index = 8
    s.extend([song(i) for i in range(10, 20)], max_len=12)
    assert len(s.tracks) == 12
    assert s.current is not None and s.current.video_id == "vid00000008"


def test_store_round_trip_and_device_limit() -> None:
    store = StateStore(":memory:", max_devices=3)
    s = PlayerState()
    s.replace([song(1)], max_len=10)
    for i in range(10):
        store.put(f"device-{i}", s)
    assert store.count() == 3
    assert store.get("device-9").tracks[0].video_id == "vid00000001"
    assert store.get("device-0").tracks == []  # evicted, starts fresh
    store.close()


def test_stream_tokens_accept_only_the_canonical_signature() -> None:
    """Audit: base64's spare bits let 16 spellings of one signature through."""
    good = tokens.make(SECRET, "dQw4w9WgXcQ", 600)
    assert tokens.check(SECRET, good) == "dQw4w9WgXcQ"
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    sig = good.rsplit(".", 1)[1]
    twins = [good[:-1] + c for c in alphabet if c != good[-1]]
    same = [t for t in twins if tokens._unb64(t.rsplit(".", 1)[1]) == tokens._unb64(sig)]
    assert len(same) == 15
    for t in same:
        with pytest.raises(tokens.BadToken):
            tokens.check(SECRET, t)


@pytest.mark.parametrize(
    ("title", "artist", "said"),
    [
        (
            "Kesariya - Film Version | Brahmāstra | Ranbir | Alia | Pritam | Arijit | Amitabh",
            "SonyMusicIndiaVEVO",
            "Kesariya - Film Version by SonyMusicIndia",
        ),
        ("Blinding Lights (Official Video)", "The Weeknd", "Blinding Lights by The Weeknd"),
        ("Tum Hi Ho [Full Song] (Lyrical) [HD]", "T-Series", "Tum Hi Ho by T-Series"),
        (
            "Kesariya (From Brahmastra)",
            "Arijit Singh",
            "Kesariya (From Brahmastra) by Arijit Singh",
        ),
        ("Bohemian Rhapsody (Remastered 2011)", "Queen - Topic", "Bohemian Rhapsody by Queen"),
        ("How to Tie a Tie", "", "How to Tie a Tie"),
        ("(Official Video)", "x", "(Official Video) by x"),  # nothing left: keep it all
        ("Lofi • beats to study // relax", "Lofi Girl", "Lofi by Lofi Girl"),
        ("Song | ", "VEVO", "Song by VEVO"),
        (
            "1 A.M Study Session 📚 [lofi hip hop]",
            "Lofi Girl",
            "1 A.M Study Session [lofi hip hop] by Lofi Girl",
        ),
        ("Kesariya ❤️ (Official Audio)", "x", "Kesariya by x"),
        ("केसरिया | Brahmastra", "अरिजीत", "केसरिया by अरिजीत"),  # vowel signs stay
    ],
)
def test_alexa_says_a_short_title(title: str, artist: str, said: str) -> None:
    """Testing 0.5.0-rc.1 on the Alexa simulator: YouTube titles were read out in full,
    "Kesariya - Film Version | Brahmāstra | Ranbir | Alia | ..." by "SonyMusicIndiaVEVO"."""
    from echo_tunes.music.catalog import Track

    track = Track("abcdefghijk", title, artist)
    assert track.spoken == said
    assert track.title == title  # the player still shows the full title
