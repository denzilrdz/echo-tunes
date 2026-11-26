from __future__ import annotations

import base64
import sys

from fastapi.testclient import TestClient

from echo_tunes.alexa.skill import Skill
from echo_tunes.dashboard import DashboardDeps, create_dashboard
from echo_tunes.history import History

from .conftest import DEVICE, directives, event, intent


async def played(skill: Skill) -> None:
    resp = await skill.handle(intent("PlayIntent", "mercedes"))
    await skill.wait_background()
    token = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", token, offsetInMilliseconds=0))


def deps(skill: Skill, **kw: object) -> DashboardDeps:
    assert skill.history is not None
    return DashboardDeps(store=skill.store, history=skill.history, signed_in=lambda: False, **kw)  # type: ignore[arg-type]


async def test_now_history_stats_and_health(skill: Skill) -> None:
    skill.history = History(":memory:", 15)
    await played(skill)
    c = TestClient(
        base_url="http://localhost:8081",
        app=create_dashboard(deps(skill, device_names={DEVICE[-12:]: "Living room"})),
    )

    now = c.get("/api/now").json()["devices"]
    assert now[0]["name"] == "Living room" and now[0]["playing"] is True
    assert now[0]["current"]["title"] == "Song 1"
    assert now[0]["source"] == 'Asked for "mercedes"'
    assert len(now[0]["up_next"]) == 9
    assert "TESTDEVICE" in now[0]["id"] and "amzn1" not in now[0]["id"]  # only the ID's tail

    hist = c.get("/api/history").json()
    assert hist["days"] == 15 and hist["plays"][0]["title"] == "Song 1"
    assert hist["plays"][0]["device_name"] == "Living room"
    assert c.get("/api/history", params={"device": "nonexistent"}).json()["plays"] == []

    assert c.get("/api/stats", params={"days": 7}).json()["plays"] == 1
    health = c.get("/api/health").json()
    assert health["status"] == "ok" and health["history_plays"] == 1

    page = c.get("/")
    assert "echo-tunes" in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert page.headers["x-frame-options"] == "DENY"
    assert c.get("/static/app.js").status_code == 200


async def test_history_follows_pause_and_next(skill: Skill) -> None:
    skill.history = History(":memory:", 15)
    resp = await skill.handle(intent("PlayIntent", "x"))
    tok = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", tok))
    await skill.handle(event("AudioPlayer.PlaybackStopped", tok, offsetInMilliseconds=42_000))
    [row] = skill.history.recent()
    assert row["status"] == "stopped" and row["played_ms"] == 42_000
    state = skill.store.get(DEVICE)
    assert state.playing is False and state.position_ms == 42_000


def test_metrics_endpoint(skill: Skill) -> None:
    skill.history = History(":memory:", 15)
    body = TestClient(base_url="http://localhost:8081", app=create_dashboard(deps(skill))).get(
        "/metrics"
    )
    assert body.status_code == 200
    text = body.text
    for name in (
        "echo_tunes_build_info",
        "echo_tunes_songs_started_total",
        "echo_tunes_resolve_seconds_bucket",
    ):
        assert name in text, name
    if sys.platform == "linux":  # process metrics read /proc
        assert "process_resident_memory_bytes" in text


def test_password(skill: Skill) -> None:
    skill.history = History(":memory:", 15)
    c = TestClient(
        base_url="http://localhost:8081", app=create_dashboard(deps(skill, password="s3cret"))
    )
    assert c.get("/api/now").status_code == 401
    assert c.get("/metrics").status_code == 401
    bad = base64.b64encode(b"admin:nope").decode()
    assert c.get("/api/now", headers={"Authorization": f"Basic {bad}"}).status_code == 401
    good = base64.b64encode(b"admin:s3cret").decode()
    assert c.get("/api/now", headers={"Authorization": f"Basic {good}"}).status_code == 200


def test_text_is_never_html(skill: Skill) -> None:
    """The page builds everything with textContent; make sure the JS has no innerHTML."""
    from importlib import resources

    js = (resources.files("echo_tunes") / "web" / "app.js").read_text()
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "eval(" not in js


async def test_setup_checks_and_test_play(skill: Skill) -> None:
    skill.history = History(":memory:", 15)
    calls = []

    async def checks() -> dict:  # type: ignore[type-arg]
        calls.append(1)
        return {
            "status": "ok",
            "checks": [{"name": "x", "status": "ok", "detail": "", "hint": "", "link": ""}],
        }

    def play() -> dict:  # type: ignore[type-arg]
        return {
            "url": skill.stream_url("dQw4w9WgXcQ", ttl_seconds=600),
            "title": "t",
            "artist": "a",
        }

    c = TestClient(
        base_url="http://localhost:8081",
        app=create_dashboard(
            deps(
                skill, run_checks=checks, test_play=play, public_origin="https://music.example.com"
            )
        ),
    )
    assert c.get("/api/setup").json()["status"] == "ok"
    c.get("/api/setup")
    c.get("/api/setup", params={"refresh": 1})  # within 10 s: still cached
    assert len(calls) == 1, "checks must not hammer YouTube"
    url = c.get("/api/test-play").json()["url"]
    assert url.startswith("https://music.example.com/stream/dQw4w9WgXcQ.")
    assert (
        "media-src 'self' https://music.example.com"
        in c.get("/").headers["content-security-policy"]
    )


def test_dns_rebinding_and_cross_site_reads_are_refused(skill: Skill) -> None:
    from echo_tunes.dashboard import host_allowed

    for ok in ("127.0.0.1:8081", "203.0.113.5", "[::1]:8081", "localhost:8081", "echo.ts.net:8443"):
        assert host_allowed(ok, frozenset({"echo.ts.net"})), ok
    for bad in ("evil.example.com", "evil.example.com:8081", "", "127.0.0.1.evil.com"):
        assert not host_allowed(bad, frozenset({"echo.ts.net"})), bad

    skill.history = History(":memory:", 15)
    c = TestClient(
        base_url="http://localhost:8081",
        app=create_dashboard(deps(skill, allowed_hosts=frozenset({"echo.ts.net"}))),
    )
    assert c.get("/api/now", headers={"Host": "evil.example.com"}).status_code == 421
    assert c.get("/api/now", headers={"Host": "echo.ts.net:8443"}).status_code == 200
    xs = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "cors"}
    assert c.get("/api/now", headers=xs).status_code == 403
    nav = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"}
    assert c.get("/", headers=nav).status_code == 200  # a link from another site still opens it
