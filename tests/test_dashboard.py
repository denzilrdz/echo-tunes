from __future__ import annotations

import base64
import re
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
    asset = re.search(r'src="\./(assets/index-[\w-]+\.js)"', page.text)
    assert asset, "index.html must load the built app from /assets/"
    js = c.get(f"/{asset.group(1)}")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    assert "immutable" in js.headers["cache-control"]  # hashed names: cached for good
    assert c.get("/static/icon.svg").status_code == 200


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


def test_built_pages_follow_the_csp(skill: Skill) -> None:
    """The committed build (web/ -> src/echo_tunes/web/dist) has no inline script or style
    (the CSP blocks them) and loads nothing from other sites."""
    from importlib import resources

    dist = resources.files("echo_tunes") / "web" / "dist"
    for name in ("index.html", "login.html"):
        page = (dist / name).read_text()
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page), name
        assert "<style" not in page and " style=" not in page, name
        assert not re.search(r'(src|href)="(https?:)?//', page), name
        for placeholder in (
            'name="application-name" content="echo-tunes"',
            'name="echo-tunes-accent" content=""',
            'name="apple-mobile-web-app-title" content="echo-tunes"',
        ):
            assert placeholder in page, (name, placeholder)  # dashboard.page_html fills these
    assert (dist / "sw.js").is_file() and (dist / "static" / "icon-192.png").is_file()


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
    assert c.get("/api/test-play").status_code == 403  # an action now: POST, with password
    assert c.post("/api/test-play", json={}).status_code == 403  # no password set
    c = TestClient(
        base_url="http://localhost:8081",
        app=create_dashboard(
            deps(skill, test_play=play, password="pw", public_origin="https://music.example.com")
        ),
        headers={"Authorization": "Basic " + base64.b64encode(b"admin:pw").decode()},
    )
    url = c.post("/api/test-play", json={}).json()["url"]
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
    from echo_tunes.dashboard import SESSION_COOKIE

    skill.history = History(":memory:", 15)
    app = create_dashboard(deps(skill, password="s3cret"))
    c = TestClient(app, base_url="http://localhost:8081", headers={"Sec-Fetch-Site": "same-origin"})
    first = c.get("/", follow_redirects=False)
    assert first.status_code == 303 and first.headers["location"] == "/login"
    assert "Sign in" in c.get("/login").text
    login = c.get("/login").text
    for public in (
        "/static/icon.svg",
        "/manifest.webmanifest",
        "/sw.js",
        *("/" + a for a in re.findall(r'"\./(assets/[^"]+)"', login)),
    ):
        assert c.get(public).status_code == 200, public  # the sign-in page needs them
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
    assert SESSION_COOKIE


def _login(app: object, password: str = "s3cret") -> tuple[TestClient, str]:  # noqa: S107
    from echo_tunes.dashboard import SESSION_COOKIE

    c = TestClient(app, base_url="http://localhost:8081")  # type: ignore[arg-type]
    r = c.post("/api/login", json={"password": password})
    assert r.status_code == 200
    return c, r.cookies[SESSION_COOKIE]


def test_sign_out_ends_the_session_even_for_a_copied_cookie(skill: Skill) -> None:
    """Audit: signing out only deleted the browser's cookie; a copy kept working."""
    from echo_tunes.dashboard import SESSION_COOKIE

    skill.history = History(":memory:", 15)
    app = create_dashboard(deps(skill, password="s3cret"))
    c, cookie = _login(app)
    other, cookie2 = _login(app)
    assert cookie != cookie2
    thief = TestClient(app, base_url="http://localhost:8081", cookies={SESSION_COOKIE: cookie})
    assert thief.get("/api/now").status_code == 200
    c.post("/api/logout", json={})
    assert thief.get("/api/now").status_code == 401
    assert other.get("/api/now").status_code == 200  # other devices stay signed in

    # "Sign out everywhere" ends every session.
    third, _ = _login(app)
    r = third.post("/api/logout/all", json={})
    assert r.status_code == 200 and r.json()["signed_out"] == 2
    assert other.get("/api/now").status_code == 401 and third.get("/api/now").status_code == 401


def test_session_cookies_are_unique_and_follow_the_current_settings() -> None:
    """Audit: SESSION_DAYS=0 gave everyone the same never-expiring cookie, and lowering
    SESSION_DAYS didn't shorten cookies already handed out."""
    from echo_tunes.sessions import Sessions

    now = [1_000_000.0]
    s = Sessions(b"k" * 32, days=0, clock=lambda: now[0])
    a, b = s.create(), s.create()
    assert a != b and s.valid(a) and s.valid(b)
    now[0] += 3650 * 86400
    assert s.valid(a)  # 0 = until signed out
    s.days = 30  # lowered (a restart with a new setting)
    assert not s.valid(a)
    fresh = s.create()
    assert s.valid(fresh)
    now[0] += 31 * 86400
    assert not s.valid(fresh)
    flipped = ("0" if fresh[-1] != "0" else "1").join((fresh[:-1], ""))
    for bad in ("", "0.abc", fresh + "x", flipped):
        assert not s.valid(bad)


def test_a_stolen_cookie_says_nothing_about_the_password() -> None:
    """Audit: the cookie was an HMAC keyed by the password, so it could be brute-forced
    offline. It is now keyed by a server secret (with the password mixed in)."""
    import hashlib
    import hmac

    from echo_tunes.sessions import Sessions, session_key

    secret = b"s" * 32
    cookie = Sessions(session_key(secret, "s3cret"), 180).create()
    sid, issued, mac = cookie.split(".")
    guess = hmac.new(b"s3cret", f"{sid}.{issued}".encode(), hashlib.sha256).hexdigest()
    assert mac != guess
    assert session_key(secret, "s3cret") != session_key(secret, "changed")
    assert session_key(secret, "s3cret") != session_key(b"t" * 32, "s3cret")


def test_sessions_survive_a_restart_and_stay_bounded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import os
    import stat

    from echo_tunes.sessions import Sessions

    path = tmp_path / "sessions.json"
    s = Sessions(b"k" * 32, 180, path, max_sessions=3)
    cookies = [s.create() for _ in range(5)]
    assert len(s) == 3
    reloaded = Sessions(b"k" * 32, 180, path, max_sessions=3)
    assert reloaded.valid(cookies[-1]) and not reloaded.valid(cookies[0])
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.write_text("{not json")
    assert len(Sessions(b"k" * 32, 180, path)) == 0  # damaged: everyone signs in again


def test_api_token_skips_the_password_queue(skill: Skill, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Audit: ~20 wrong passwords in flight made monitors' Basic-auth scrapes get 429."""
    import asyncio

    import httpx

    from echo_tunes import dashboard

    monkeypatch.setattr(dashboard, "WRONG_PASSWORD_DELAY", 0.2)
    monkeypatch.setattr(dashboard, "MAX_QUEUED_CHECKS", 2)
    skill.history = History(":memory:", 15)
    token = "t" * 40
    app = create_dashboard(deps(skill, password="s3cret", api_token=token))

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8081") as c:
            bad = base64.b64encode(b"admin:nope").decode()
            flood = [
                asyncio.create_task(c.get("/metrics", headers={"Authorization": f"Basic {bad}"}))
                for _ in range(6)
            ]
            await asyncio.sleep(0.05)
            t0 = time.monotonic()
            ok = await c.get("/metrics", headers={"Authorization": f"Bearer {token}"})
            assert ok.status_code == 200 and time.monotonic() - t0 < 0.15
            wrong = await c.get("/metrics", headers={"Authorization": "Bearer " + "x" * 40})
            assert wrong.status_code == 401
            await asyncio.gather(*flood)

    asyncio.run(run())


def test_api_token_must_be_long(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import pytest
    from pydantic import ValidationError

    from echo_tunes.config import Settings

    monkeypatch.setenv("ECHO_TUNES_PUBLIC_URL", "https://music.example.com")
    monkeypatch.setenv("ECHO_TUNES_SKILL_IDS", "amzn1.ask.skill.x")
    monkeypatch.setenv("ECHO_TUNES_DASHBOARD_API_TOKEN", "short")
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(_env_file=None)  # type: ignore[call-arg]
    monkeypatch.setenv("ECHO_TUNES_DASHBOARD_API_TOKEN", "a" * 64)
    assert Settings(_env_file=None).dashboard_api_token is not None  # type: ignore[call-arg]


def test_huge_bodies_are_refused_before_they_are_read(skill: Skill) -> None:
    """Audit: a 400 MB POST /api/login grew the process to 1.9 GB, and the 422 echoed it back."""
    skill.history = History(":memory:", 15)
    c = TestClient(
        create_dashboard(deps(skill, password="s3cret")), base_url="http://localhost:8081"
    )
    big = b'{"password": "' + b"x" * (300 * 1024) + b'"}'
    hdrs = {"Content-Type": "application/json"}
    assert c.post("/api/login", content=big, headers=hdrs).status_code == 413

    def chunked():  # type: ignore[no-untyped-def]
        yield b'{"password": "'
        for _ in range(40):
            yield b"x" * 10_000
        yield b'"}'

    r = c.post("/api/login", content=chunked(), headers=hdrs)
    assert r.status_code == 413
    # Validation errors are short and never repeat the input.
    long = '{"password": "' + "y" * 5000 + '"}'
    r = c.post("/api/login", content=long, headers=hdrs)
    assert r.status_code == 422 and len(r.content) < 300 and "yyyy" not in r.text


def test_history_offset_is_bounded(skill: Skill) -> None:
    skill.history = History(":memory:", 15)
    c = TestClient(create_dashboard(deps(skill)), base_url="http://localhost:8081")
    assert c.get("/api/history", params={"offset": 10**30}).status_code == 422
    assert c.get("/api/history", params={"offset": 1000}).status_code == 200


def test_wrong_passwords_are_slowed_down_but_never_lock_out(skill: Skill, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Security review: a per-address lockout let one device behind the same reverse proxy lock
    everyone out, and wrong Basic-auth passwords weren't limited at all."""
    from echo_tunes import dashboard

    delay = 0.2
    monkeypatch.setattr(dashboard, "WRONG_PASSWORD_DELAY", delay)
    skill.history = History(":memory:", 15)
    c = TestClient(
        create_dashboard(deps(skill, password="s3cret")), base_url="http://localhost:8081"
    )
    bad = base64.b64encode(b"admin:nope").decode()
    t0 = time.monotonic()
    for _ in range(2):
        assert c.post("/api/login", json={"password": "x"}).status_code == 401
        assert c.get("/api/now", headers={"Authorization": f"Basic {bad}"}).status_code == 401
    assert time.monotonic() - t0 >= 4 * delay  # every wrong try waited
    t0 = time.monotonic()
    assert c.post("/api/login", json={"password": "s3cret"}).status_code == 200  # never locked out
    assert time.monotonic() - t0 < delay / 2  # a right one doesn't wait


def test_a_session_can_last_until_signed_out(skill: Skill) -> None:
    skill.history = History(":memory:", 15)
    app = create_dashboard(deps(skill, password="s3cret", session_days=0))
    c = TestClient(app, base_url="http://localhost:8081")
    first = c.post("/api/login", json={"password": "s3cret"}).headers["set-cookie"]
    assert f"Max-Age={400 * 86400}" in first
    value = first.split(";")[0]
    import time as _time

    _time.sleep(1.1)  # the renewed cookie carries a new issue time
    renewed = c.get("/")  # every visit renews the browser's cookie (same session)
    fresh = renewed.headers["set-cookie"].split(";")[0]
    assert (
        renewed.status_code == 200
        and fresh != value
        and f"Max-Age={400 * 86400}" in renewed.headers["set-cookie"]
    )
    assert c.get("/api/now").status_code == 200  # the new cookie works...
    old = TestClient(
        app, base_url="http://localhost:8081", cookies={value.split("=")[0]: value.split("=", 1)[1]}
    )
    assert old.get("/api/now").status_code == 401  # ...and the old one was retired
    assert c.post("/api/logout", json={}).status_code == 200
    assert c.get("/api/now").status_code == 401  # signing out ends the renewed session too


def test_renewing_the_same_cookie_twice_does_not_fork_the_session() -> None:
    """Security review: two renewals of one cookie must not leave two live sessions."""
    from echo_tunes.sessions import Sessions

    now = [1_000_000.0]
    s = Sessions(b"k" * 32, 0, clock=lambda: now[0])
    first = s.create()
    now[0] += 5
    a = s.renew(first)
    b = s.renew(first)  # a second page load racing with the same old cookie
    assert a is not None and b is None
    assert s.revoke(a) and not s.valid(a)


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
