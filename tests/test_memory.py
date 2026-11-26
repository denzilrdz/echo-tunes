"""Soak test: thousands of requests must not make memory grow.

Simulates weeks of listening (play, events, skips, streams) on many devices and checks Python's
own allocation tracker: after a warm-up round, further rounds must not keep allocating.
"""

from __future__ import annotations

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
