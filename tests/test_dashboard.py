from __future__ import annotations

import base64
import sys
import time

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
    for bad in (
        "evil.example.com",
        "evil.example.com:8081",
        "",
        "127.0.0.1.evil.com",
        "[::1]evil.example.com",
        "[::1",
        "127.0.0.1:80x",
    ):
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


def test_sign_in_once_with_a_long_lived_cookie(skill: Skill) -> None:
    from echo_tunes.dashboard import SESSION_COOKIE, session_valid, session_value

    skill.history = History(":memory:", 15)
    app = create_dashboard(deps(skill, password="s3cret"))
    c = TestClient(app, base_url="http://localhost:8081", headers={"Sec-Fetch-Site": "same-origin"})
    first = c.get("/", follow_redirects=False)
    assert first.status_code == 303 and first.headers["location"] == "/login"
    assert "Sign in" in c.get("/login").text
    for public in ("/static/app.css", "/manifest.webmanifest", "/sw.js"):
        assert c.get(public).status_code == 200, public
    browser = c.get("/api/now", headers={"Sec-Fetch-Mode": "cors"})
    assert browser.status_code == 401 and "www-authenticate" not in browser.headers  # no pop-up

    assert c.post("/api/login", json={"password": "nope"}).status_code == 401
    ok = c.post("/api/login", json={"password": "s3cret"})
    assert ok.status_code == 200
    cookie = ok.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and f"Max-Age={180 * 86400}" in cookie
    assert c.get("/api/now").status_code == 200  # the cookie is enough from now on
    assert c.get("/", follow_redirects=False).status_code == 200
    assert c.get("/login", follow_redirects=False).status_code == 303

    c.post("/api/logout", json={})
    assert c.get("/api/now").status_code == 401

    # Sessions expire, and changing the password signs everyone out.
    v = session_value("s3cret", 2_000_000_000)
    assert session_valid("s3cret", v, 1_900_000_000)
    assert not session_valid("s3cret", v, 2_000_000_001)
    assert not session_valid("changed", v, 1_900_000_000)
    assert not session_valid("s3cret", "9999999999.forged", 0)
    assert not session_valid("s3cret", "", 0)
    assert SESSION_COOKIE


def test_wrong_passwords_are_slowed_down_but_never_lock_out(skill: Skill, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Security review: a per-address lockout let one device behind the same reverse proxy lock
    everyone out, and wrong Basic-auth passwords weren't limited at all."""
    from echo_tunes import dashboard

    monkeypatch.setattr(dashboard, "WRONG_PASSWORD_DELAY", 0.05)
    skill.history = History(":memory:", 15)
    c = TestClient(
        create_dashboard(deps(skill, password="s3cret")), base_url="http://localhost:8081"
    )
    bad = base64.b64encode(b"admin:nope").decode()
    t0 = time.monotonic()
    for _ in range(4):
        assert c.post("/api/login", json={"password": "x"}).status_code == 401
        assert c.get("/api/now", headers={"Authorization": f"Basic {bad}"}).status_code == 401
    assert time.monotonic() - t0 >= 8 * 0.05  # every wrong try waited
    t0 = time.monotonic()
    assert c.post("/api/login", json={"password": "s3cret"}).status_code == 200  # never locked out
    assert time.monotonic() - t0 < 0.05


def test_a_session_can_last_until_signed_out(skill: Skill) -> None:
    from echo_tunes.dashboard import session_valid, session_value

    skill.history = History(":memory:", 15)
    app = create_dashboard(deps(skill, password="s3cret", session_days=0))
    c = TestClient(app, base_url="http://localhost:8081")
    first = c.post("/api/login", json={"password": "s3cret"}).headers["set-cookie"]
    assert "echo_tunes_session=0." in first and f"Max-Age={400 * 86400}" in first
    again = c.get("/")  # every visit renews the browser's cookie
    assert again.status_code == 200 and "echo_tunes_session=0." in again.headers["set-cookie"]
    assert session_valid("s3cret", session_value("s3cret", 0), 4_000_000_000)
    assert not session_valid("other", session_value("s3cret", 0), 0)


async def test_parallel_guesses_still_take_turns(skill: Skill, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Security review: guesses sent at once were all compared at once (only their answers
    waited). Each check must wait for its turn before it's compared; a full queue gets 429."""
    import asyncio

    import httpx

    from echo_tunes import dashboard

    monkeypatch.setattr(dashboard, "WRONG_PASSWORD_DELAY", 0.05)
    skill.history = History(":memory:", 15)
    app = create_dashboard(deps(skill, password="s3cret"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8081") as c:
        t0 = time.monotonic()
        rs = await asyncio.gather(
            *(c.post("/api/login", json={"password": f"x{i}"}) for i in range(6))
        )
        assert [r.status_code for r in rs] == [401] * 6
        assert time.monotonic() - t0 >= 6 * 0.05  # one at a time

        monkeypatch.setattr(dashboard, "MAX_QUEUED_CHECKS", 2)
        bad = base64.b64encode(b"admin:nope").decode()
        rs = await asyncio.gather(
            *(c.get("/api/now", headers={"Authorization": f"Basic {bad}"}) for _ in range(5))
        )
        codes = sorted(r.status_code for r in rs)
        assert codes.count(429) >= 1 and set(codes) <= {401, 429}
