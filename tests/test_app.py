"""End to end over HTTP: signed Alexa request in, Play directive out, audio streamed."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from echo_tunes.alexa.skill import Skill
from echo_tunes.alexa.verify import AlexaVerifier
from echo_tunes.app import Services, create_app
from echo_tunes.stream import StreamRelay

from .conftest import SECRET, SKILL_ID, FakeAmazon, intent
from .test_stream import AUDIO, OneSource, cdn


def client(skill: Skill, amazon: FakeAmazon) -> TestClient:
    services = Services(
        skill=skill,
        verifier=AlexaVerifier([SKILL_ID], store=amazon.store, fetch=amazon.fetch),
        relay=StreamRelay(OneSource(), cdn()),
        stream_secret=SECRET,
    )
    return TestClient(create_app(services=services))


def test_play_then_stream(skill: Skill) -> None:
    amazon = FakeAmazon()
    with client(skill, amazon) as c:
        body = json.dumps(intent("PlayIntent", "tum hi ho")).encode()
        resp = c.post("/alexa", content=body, headers=amazon.headers(body))
        assert resp.status_code == 200
        url = resp.json()["response"]["directives"][0]["audioItem"]["stream"]["url"]
        path = httpx.URL(url).path

        audio = c.get(path, headers={"Range": "bytes=0-"})
        assert audio.status_code == 206
        assert audio.headers["content-type"] == "audio/mp4"
        assert audio.headers["content-range"] == f"bytes 0-{len(AUDIO) - 1}/{len(AUDIO)}"
        assert audio.content == AUDIO

        head = c.head(path)
        assert head.status_code == 200 and head.headers["content-length"] == str(len(AUDIO))


def test_unsigned_or_forged_requests_are_refused(skill: Skill) -> None:
    amazon = FakeAmazon()
    with client(skill, amazon) as c:
        body = json.dumps(intent("PlayIntent", "x")).encode()
        assert c.post("/alexa", content=body).status_code == 400
        forged = amazon.headers(b"something else")
        assert c.post("/alexa", content=body, headers=forged).status_code == 400
        too_big = b"{" + b" " * 300_000 + b"}"
        assert c.post("/alexa", content=too_big, headers=amazon.headers(too_big)).status_code == 400


def test_unsatisfiable_range_reports_the_size(skill: Skill) -> None:
    from echo_tunes import tokens

    with client(skill, FakeAmazon()) as c:
        path = f"/stream/{tokens.make(SECRET, 'dQw4w9WgXcQ', 600)}.m4a"
        r = c.get(path, headers={"Range": f"bytes={len(AUDIO) + 10}-"})
        assert r.status_code == 416 and r.headers["content-range"] == f"bytes */{len(AUDIO)}"


def test_rejections_are_logged_at_most_once_per_reason_in_a_while(caplog) -> None:  # type: ignore[no-untyped-def]
    """Audit: every rejected request wrote a log line, so a flood could fill the disk."""
    import logging

    from echo_tunes.app import RateLimitedLog

    now = [0.0]
    rl = RateLimitedLog(every=10, clock=lambda: now[0])
    with caplog.at_level(logging.WARNING, logger="echo_tunes.app"):
        for _ in range(100):
            rl.warning("signature", "rejected: %s", "bad")
        rl.warning("timestamp", "rejected: %s", "old")
        now[0] = 11
        rl.warning("signature", "rejected: %s", "bad")
    lines = [r.getMessage() for r in caplog.records]
    assert lines == [
        "rejected: bad",
        "rejected: old",
        "rejected: bad (and 99 more like it since the last message)",
    ]


async def test_a_body_that_trickles_in_is_cut_off(skill: Skill, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    from echo_tunes import app as app_mod

    monkeypatch.setattr(app_mod, "BODY_READ_TIMEOUT", 0.1)
    services = Services(
        skill=skill,
        verifier=AlexaVerifier([SKILL_ID], store=FakeAmazon().store),
        relay=StreamRelay(OneSource(), cdn()),
        stream_secret=SECRET,
    )
    app = create_app(services=services)
    app.state.services = services
    sent: list[dict] = []  # type: ignore[type-arg]

    async def receive() -> dict:  # type: ignore[type-arg]
        await asyncio.sleep(0.05)  # a byte now and then, forever
        return {"type": "http.request", "body": b" ", "more_body": True}

    async def send(message: dict) -> None:  # type: ignore[type-arg]
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "https", "path": "/alexa", "raw_path": b"/alexa", "query_string": b"",
        "root_path": "", "headers": [(b"transfer-encoding", b"chunked")],
        "client": ("1.2.3.4", 1), "server": ("test", 443), "state": {},
    }  # fmt: skip
    await asyncio.wait_for(app(scope, receive, send), 2)
    assert sent[0]["status"] == 400


def test_stream_needs_a_valid_token(skill: Skill) -> None:
    with client(skill, FakeAmazon()) as c:
        assert c.get("/stream/dQw4w9WgXcQ.9999999999.AAAAAAAAAAAAAAAAAAAAAA.m4a").status_code == 404
        assert c.get("/stream/nonsense.m4a").status_code == 404


def test_health(skill: Skill) -> None:
    with client(skill, FakeAmazon()) as c:
        data = c.get("/healthz").json()
        assert data["status"] == "ok" and data["memory_mb"] > 0


async def test_chunked_body_without_length_is_capped(skill: Skill) -> None:
    """A chunked upload has no Content-Length; the server must stop reading at the limit."""
    services = Services(
        skill=skill,
        verifier=AlexaVerifier([SKILL_ID], store=FakeAmazon().store),
        relay=StreamRelay(OneSource(), cdn()),
        stream_secret=SECRET,
    )
    app = create_app(services=services)
    app.state.services = services  # what the lifespan does; called directly here
    pulled = [0]
    sent: list[dict] = []  # type: ignore[type-arg]

    async def receive() -> dict:  # type: ignore[type-arg]
        pulled[0] += 1  # 10,000 x 64 KB = 640 MB if fully read
        return {"type": "http.request", "body": b" " * 65536, "more_body": pulled[0] < 10_000}

    async def send(message: dict) -> None:  # type: ignore[type-arg]
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/alexa",
        "raw_path": b"/alexa",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"transfer-encoding", b"chunked")],
        "client": ("1.2.3.4", 1),
        "server": ("test", 443),
        "state": {},
    }
    await app(scope, receive, send)
    assert sent[0]["status"] == 400
    assert pulled[0] <= 6  # stopped just past 256 KB
