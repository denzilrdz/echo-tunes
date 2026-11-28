"""Searching all of YouTube: result checking, the cache and the time limit."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from echo_tunes.music import youtube
from echo_tunes.music.catalog import YTMusicCatalog
from echo_tunes.music.youtube import YouTubeSearch


def entry(vid: str = "HXJx8j7JpKY", **over: Any) -> dict[str, Any]:
    raw = {
        "id": vid,
        "title": "How to Tie a Tie",
        "channel": "Tie Channel",
        "uploader": "Tie Channel",
        "duration": 181.0,
        "live_status": None,
        "thumbnails": [
            {"url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", "width": 480, "height": 270}
        ],
    }
    return raw | over


def test_parse_keeps_what_the_player_needs() -> None:
    item = youtube.parse(entry())
    assert item is not None
    assert (item.kind, item.id, item.title, item.subtitle, item.duration) == (
        "song",
        "HXJx8j7JpKY",
        "How to Tie a Tie",
        "Tie Channel",
        181,
    )
    assert item.image == "https://i.ytimg.com/vi/HXJx8j7JpKY/hqdefault.jpg"


@pytest.mark.parametrize(
    "bad",
    [
        {"live_status": "is_live", "duration": None},  # HLS only: the relay can't play it
        {"live_status": "is_upcoming"},
        {"duration": None},
        {"duration": 0},
        {"id": "not a video id"},
        {"id": "PLxxxxxxxxxxxxxxxx"},  # a playlist in the results
    ],
)
def test_parse_drops_what_cant_play(bad: dict[str, Any]) -> None:
    assert youtube.parse(entry(**bad)) is None


def test_parse_drops_images_from_other_hosts_and_long_text() -> None:
    item = youtube.parse(
        entry(
            title="x" * 500,
            thumbnails=[{"url": "https://evil.example.com/a.jpg", "width": 480}],
        )
    )
    assert item is not None and item.image is None and len(item.title) == 200


def test_parse_all_dedupes_and_ignores_junk() -> None:
    items = youtube.parse_all([entry(), entry(), None, "x", entry("abcdefghijk")])
    assert [i.id for i in items] == ["HXJx8j7JpKY", "abcdefghijk"]
    assert youtube.parse_all({"not": "a list"}) == []


async def test_search_cleans_the_query_and_caches() -> None:
    calls: list[tuple[str, int]] = []

    async def fake(q: str, limit: int) -> list[dict[str, Any]]:
        calls.append((q, limit))
        return [entry()]

    s = YouTubeSearch(fake)
    first = await s.search("  How to\ntie   a tie ")
    again = await s.search("how to tie a TIE")
    assert first == again and len(first) == 1
    assert calls == [("How to tie a tie", youtube.RESULTS)]
    assert await s.search("   ") == []
    assert len(calls) == 1


async def test_search_has_a_total_time_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(youtube, "BUDGET", 0.05)

    async def stuck(q: str, limit: int) -> list[dict[str, Any]]:
        await asyncio.sleep(10)
        return []

    with pytest.raises(TimeoutError):
        await YouTubeSearch(stuck).search("anything")


async def test_catalog_uses_youtube_for_videos_only() -> None:
    async def fake(q: str, limit: int) -> list[dict[str, Any]]:
        return [entry(live_status="is_live", duration=None, id="livelivexxx"), entry()]

    class NoYTMusic:
        def search(self, *a: Any, **k: Any) -> list[Any]:
            raise AssertionError("YouTube Music shouldn't be asked")

    cat = YTMusicCatalog(NoYTMusic(), False, youtube=YouTubeSearch(fake))
    try:
        track = await cat.search_video("tie")
        assert track is not None and track.video_id == "HXJx8j7JpKY"
        assert track.artist == "Tie Channel" and track.duration == 181
        assert [i.id for i in await cat.search_items("tie", "video")] == ["HXJx8j7JpKY"]
        plain = YTMusicCatalog(NoYTMusic(), False)
        assert await plain.search_video("tie") is None
        assert await plain.search_items("tie", "video") == []
        plain.close()
    finally:
        cat.close()
