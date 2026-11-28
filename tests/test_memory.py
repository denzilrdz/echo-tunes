"""Soak test: thousands of requests must not make memory grow.

Simulates weeks of listening (play, events, skips, streams) on many devices and checks Python's
own allocation tracker: after a warm-up round, further rounds must not keep allocating.
"""

from __future__ import annotations

import asyncio
import gc
import json
import tracemalloc

from fastapi.testclient import TestClient

from echo_tunes.alexa.skill import Skill
from echo_tunes.alexa.verify import AlexaVerifier
from echo_tunes.app import Services, create_app
from echo_tunes.stream import StreamRelay

from .conftest import SECRET, SKILL_ID, FakeAmazon, envelope, event, intent
from .test_stream import OneSource, cdn

ROUNDS = 300
ALLOWED_GROWTH_KB = 512


def one_round(c: TestClient, amazon: FakeAmazon, n: int) -> None:
    def post(env: dict) -> dict:  # type: ignore[type-arg]
        env["context"]["System"]["device"]["deviceId"] = f"device-{n % 80}"  # > store limit
        body = json.dumps(env).encode()
        resp = c.post("/alexa", content=body, headers=amazon.headers(body))
        assert resp.status_code == 200
        return resp.json()  # type: ignore[no-any-return]

    resp = post(intent("PlayIntent", f"song number {n}"))
    item = resp["response"]["directives"][0]["audioItem"]["stream"]
    post(event("AudioPlayer.PlaybackStarted", item["token"]))
    c.get(item["url"].removeprefix("https://music.example.com"), headers={"Range": "bytes=0-"})
    post(event("AudioPlayer.PlaybackNearlyFinished", item["token"]))
    post(intent("AMAZON.NextIntent"))
    post(envelope({"type": "PlaybackController.NextCommandIssued"}))
    post(intent("WhatsPlayingIntent"))
    post(intent("PlayYouTubeIntent", f"video number {n} on youtube"))


def test_memory_stays_flat(skill: Skill) -> None:
    amazon = FakeAmazon()
    services = Services(
        skill=skill,
        verifier=AlexaVerifier([SKILL_ID], store=amazon.store, fetch=amazon.fetch),
        relay=StreamRelay(OneSource(), cdn()),
        stream_secret=SECRET,
    )
    with TestClient(create_app(services=services)) as c:
        for n in range(50):  # warm-up: caches fill, imports finish
            one_round(c, amazon, n)
        gc.collect()
        tracemalloc.start()
        base = tracemalloc.take_snapshot()
        for n in range(50, 50 + ROUNDS):
            one_round(c, amazon, n)
        gc.collect()
        after = tracemalloc.take_snapshot()
        tracemalloc.stop()

    growth = sum(s.size_diff for s in after.compare_to(base, "filename"))
    top = "\n".join(str(s) for s in after.compare_to(base, "lineno")[:8])
    assert growth < ALLOWED_GROWTH_KB * 1024, f"grew {growth / 1024:.0f} KB:\n{top}"


async def test_youtube_search_cache_stays_bounded() -> None:
    """The real YouTubeSearch (the soak above uses a fake catalog): thousands of different
    searches keep at most its cache's worth of results."""
    from echo_tunes.music.youtube import YouTubeSearch

    async def fake(query: str, limit: int) -> list[dict]:  # type: ignore[type-arg]
        return [
            {"id": f"{i:011d}", "title": f"{query} {i}", "channel": "c", "duration": 60}
            for i in range(limit)
        ]

    s = YouTubeSearch(fake)
    # Trace from the start: the cache replaces every entry, and freeing entries made before
    # tracing began wouldn't be counted against the new ones.
    tracemalloc.start()
    for n in range(300):  # warm-up: past the cache's 128 places, so it's full
        await s.search(f"warm query {n:04d}")
        await asyncio.sleep(0)
    gc.collect()
    base = tracemalloc.take_snapshot()
    for n in range(3000):
        await s.search(f"same length {n:04d}")
        await asyncio.sleep(0)  # let the loop run, as a server's does (it clears old timers)
    gc.collect()
    grown = sum(st.size_diff for st in tracemalloc.take_snapshot().compare_to(base, "filename"))
    tracemalloc.stop()
    assert len(s._cache) <= 128
    assert grown < ALLOWED_GROWTH_KB * 1024, f"grew {grown / 1024:.0f} KB"
