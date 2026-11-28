"""Signing in to the dashboard with a Google account (the device flow), against a fake Google."""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from echo_tunes import google_login
from echo_tunes.alexa.skill import Skill
from echo_tunes.dashboard import SESSION_COOKIE, DashboardDeps, create_dashboard
from echo_tunes.google_login import GoogleLogin, GoogleLoginError
from echo_tunes.history import History

CLIENT = "client-123.apps.googleusercontent.com"
ALLOWED = frozenset({"me@example.com"})


def id_token(**over: Any) -> str:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT,
        "exp": int(time.time()) + 3600,
        "email": "Me@Example.com",
        "email_verified": True,
    } | over
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJSUzI1NiJ9.{body}.c2ln"


class FakeGoogle:
    """Answers the device-code and token endpoints like Google does."""

    def __init__(self) -> None:
        self.answers: list[dict[str, Any]] = []  # what the token endpoint says next
        self.token_calls = 0
        self.device_calls: list[dict[str, str]] = []
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("no route")
        form = dict(httpx.QueryParams(request.content.decode()))
        if str(request.url) == google_login.DEVICE_CODE_URL:
            self.device_calls.append(form)
            return httpx.Response(
                200,
                json={
                    "device_code": f"dev-{len(self.device_calls)}",
                    "user_code": "ABCD-EFGH",
                    "verification_url": "https://www.google.com/device",
                    "expires_in": 1800,
                    "interval": 5,
                },
            )
        assert str(request.url) == google_login.TOKEN_URL
        assert form["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
        self.token_calls += 1
        answer = self.answers.pop(0) if self.answers else {"error": "authorization_pending"}
        return httpx.Response(400 if "error" in answer else 200, json=answer)

    def login(self, emails: frozenset[str] = ALLOWED) -> GoogleLogin:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        return GoogleLogin(CLIENT, "secret", emails, http)


def due(g: GoogleLogin) -> None:
    """Skip the wait Google asks for between checks."""
    for flow in g._flows.values():
        flow.next_poll = 0


@pytest.fixture
def google() -> FakeGoogle:
    return FakeGoogle()


# --- the flow itself ----------------------------------------------------------------------
async def test_approved_code_signs_in_an_allowed_account(google: FakeGoogle) -> None:
    g = google.login()
    started = await g.start()
    assert started["code"] == "ABCD-EFGH" and started["url"] == "https://www.google.com/device"
    assert started["expires_in"] == google_login.FLOW_SECONDS  # ours is shorter than Google's
    assert google.device_calls == [{"client_id": CLIENT, "scope": "openid email"}]
    assert await g.poll(started["flow"]) is None  # too soon: Google isn't even asked
    assert google.token_calls == 0
    due(g)
    assert await g.poll(started["flow"]) is None  # authorization_pending
    google.answers.append({"access_token": "x", "id_token": id_token()})
    due(g)
    assert await g.poll(started["flow"]) == "me@example.com"
    assert len(g) == 0  # finished flows are forgotten
    with pytest.raises(GoogleLoginError) as gone:
        await g.poll(started["flow"])  # can't be used twice
    assert gone.value.status == 410
    await g.aclose()


async def test_slow_down_makes_checks_rarer(google: FakeGoogle) -> None:
    g = google.login()
    flow = (await g.start())["flow"]
    google.answers.append({"error": "slow_down"})
    due(g)
    assert await g.poll(flow) is None
    assert g._flows[flow].interval == 10
    await g.aclose()


@pytest.mark.parametrize(
    ("answer", "status"),
    [
        ({"error": "access_denied"}, 403),
        ({"error": "expired_token"}, 410),
        ({"error": "invalid_client"}, 502),
        ({"id_token": id_token(email="someone@else.com")}, 403),  # not on the list
        ({"id_token": id_token(aud="another-client")}, 502),
        ({"id_token": id_token(iss="https://evil.example.com")}, 502),
        ({"id_token": id_token(email_verified=False)}, 502),
        ({"id_token": id_token(exp=int(time.time()) - 3600)}, 502),
        ({"id_token": id_token(email=["me@example.com"])}, 502),
        ({"id_token": "not.a-jwt"}, 502),
        ({"id_token": "a.!!!.c"}, 502),
        ({"access_token": "no identity"}, 502),
    ],
)
async def test_refusals(google: FakeGoogle, answer: dict[str, Any], status: int) -> None:
    g = google.login()
    flow = (await g.start())["flow"]
    google.answers.append(answer)
    due(g)
    with pytest.raises(GoogleLoginError) as refused:
        await g.poll(flow)
    assert refused.value.status == status
    assert len(g) == 0
    await g.aclose()


async def test_pending_sign_ins_are_capped_and_in_use_ones_are_never_pushed_out(
    google: FakeGoogle, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(google_login.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(google_login, "MAX_STARTS", 100)  # tested on its own below
    g = google.login()
    mine = (await g.start())["flow"]
    for _ in range(google_login.MAX_PENDING - 1):
        await g.start()
    calls = len(google.device_calls)
    with pytest.raises(GoogleLoginError) as full:  # all fresh: refused, Google not asked
        await g.start()
    assert full.value.status == 429 and len(google.device_calls) == calls
    # Someone walks away from theirs; this page keeps checking on its own.
    clock[0] += google_login.STALE_SECONDS + 1
    assert await g.poll(mine) is None
    for _ in range(google_login.MAX_PENDING - 1):
        await g.start()  # each pushes out an abandoned one
    assert mine in g._flows and len(g) == google_login.MAX_PENDING
    with pytest.raises(GoogleLoginError):  # the rest are fresh now: refused
        await g.start()
    assert mine in g._flows
    # Everything expires.
    clock[0] += google_login.FLOW_SECONDS + 1
    with pytest.raises(GoogleLoginError):
        await g.poll(mine)
    assert len(g) == 0
    await g.aclose()


async def test_a_sign_in_survives_its_page_being_suspended(
    google: FakeGoogle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review of #28: a phone suspends the sign-in page while you approve the code in another
    tab; it came back to "This sign-in code expired" although Google had approved it."""
    clock = [1000.0]
    monkeypatch.setattr(google_login.time, "monotonic", lambda: clock[0])
    g = google.login()
    flow = (await g.start())["flow"]
    clock[0] += 5 * 60  # five quiet minutes: approving on another tab, phone asleep
    google.answers.append({"id_token": id_token()})
    assert await g.poll(flow) == "me@example.com"
    await g.aclose()


async def test_starts_are_rate_limited(google: FakeGoogle, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr(google_login.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(google_login, "MAX_PENDING", 100)  # room is never the limit here
    g = google.login()
    for _ in range(google_login.MAX_STARTS):
        await g.start()
    with pytest.raises(GoogleLoginError) as limited:
        await g.start()
    assert limited.value.status == 429 and "minute" in limited.value.message
    assert len(google.device_calls) == google_login.MAX_STARTS
    clock[0] += 60
    await g.start()
    await g.aclose()


async def test_google_unreachable(google: FakeGoogle) -> None:
    g = google.login()
    google.down = True
    with pytest.raises(GoogleLoginError) as down:
        await g.start()
    assert down.value.status == 502
    await g.aclose()


# --- through the dashboard ---------------------------------------------------------------
def dashboard(
    skill: Skill,
    google: FakeGoogle,
    password: str | None = "s3cret",  # noqa: S107
) -> tuple[TestClient, GoogleLogin]:
    skill.history = History(":memory:", 15)
    g = google.login()
    deps = DashboardDeps(
        store=skill.store,
        history=skill.history,
        signed_in=lambda: False,
        password=password,
        google=g,
    )
    c = TestClient(
        create_dashboard(deps),
        base_url="http://192.0.2.10:8081",  # a LAN address: no HTTPS, no domain name
        headers={"Sec-Fetch-Site": "same-origin"},
    )
    return c, g


def test_sign_in_with_google_gets_the_same_session_as_the_password(
    skill: Skill, google: FakeGoogle
) -> None:
    c, g = dashboard(skill, google)
    assert c.get("/api/now").status_code == 401
    assert c.get("/api/login/options").json() == {"google": True}  # open before signing in
    started = c.post("/api/login/google", json={}).json()
    assert started["code"] == "ABCD-EFGH" and "flow" in started
    r = c.post("/api/login/google/poll", json={"flow": started["flow"]})
    assert r.status_code == 202 and r.json() == {"status": "pending"}
    assert SESSION_COOKIE not in r.cookies
    google.answers.append({"id_token": id_token()})
    due(g)
    ok = c.post("/api/login/google/poll", json={"flow": started["flow"]})
    assert ok.status_code == 200 and SESSION_COOKIE in ok.cookies
    assert "HttpOnly" in ok.headers["set-cookie"]
    assert c.get("/api/now").status_code == 200
    # The password still works on its own.
    c2 = TestClient(c.app, base_url="http://192.0.2.10:8081")
    assert c2.post("/api/login", json={"password": "s3cret"}).status_code == 200


def test_a_refused_account_gets_no_session(skill: Skill, google: FakeGoogle) -> None:
    c, g = dashboard(skill, google)
    flow = c.post("/api/login/google", json={}).json()["flow"]
    google.answers.append({"id_token": id_token(email="stranger@example.com")})
    due(g)
    r = c.post("/api/login/google/poll", json={"flow": flow})
    assert r.status_code == 403 and "ECHO_TUNES_DASHBOARD_GOOGLE_EMAILS" in r.json()["detail"]
    assert SESSION_COOKIE not in r.cookies
    assert c.get("/api/now").status_code == 401


def test_google_sign_in_is_off_without_a_password(skill: Skill, google: FakeGoogle) -> None:
    c, _ = dashboard(skill, google, password=None)
    assert c.get("/api/login/options").json() == {"google": False}
    assert c.post("/api/login/google", json={}).status_code == 404
    assert google.device_calls == []


def test_google_sign_in_refuses_other_sites_and_bad_input(skill: Skill, google: FakeGoogle) -> None:
    c, _ = dashboard(skill, google)
    cross = {"Sec-Fetch-Site": "cross-site"}
    assert c.post("/api/login/google", json={}, headers=cross).status_code == 403
    assert c.post("/api/login/google", content=b"x").status_code == 415  # JSON only
    assert c.post("/api/login/google/poll", json={"flow": "short"}).status_code == 422
    assert c.post("/api/login/google/poll", json={"flow": "x" * 40}).status_code == 410
    assert google.device_calls == []


async def test_odd_numbers_from_google_fall_back_to_defaults() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"device_code": "d", "user_code": "C", "interval": "soon", "expires_in": None},
        )

    g = GoogleLogin(CLIENT, "s", ALLOWED, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    started = await g.start()
    assert started["interval"] == 5.0 and started["expires_in"] == google_login.FLOW_SECONDS
    await g.aclose()


def test_taking_an_email_off_the_list_signs_that_account_out(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Review of #28: Google sessions outlived their place on the list (up to 180 days)."""
    from echo_tunes.sessions import Sessions

    path = tmp_path / "sessions.json"
    key = b"k" * 32
    both = frozenset({"me@example.com", "partner@example.com"})
    s = Sessions(key, 180, path, google_emails=both)
    password = s.create()
    me = s.create(email="Me@Example.com")
    partner = s.create(email="partner@example.com")
    assert s.valid(password) and s.valid(me) and s.valid(partner)
    # Restart with the partner removed from ECHO_TUNES_DASHBOARD_GOOGLE_EMAILS.
    s = Sessions(key, 180, path, google_emails=frozenset({"me@example.com"}))
    assert s.valid(password) and s.valid(me)
    assert not s.valid(partner)
    assert s.renew(partner) is None
    # Google sign-in turned off: only password sessions remain.
    s = Sessions(key, 180, path)
    assert s.valid(password) and not s.valid(me)
    assert len(s) == 1


def test_sessions_saved_before_google_sign_in_still_load(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from echo_tunes.sessions import Sessions

    path = tmp_path / "sessions.json"
    old = Sessions(b"k" * 32, 180, path)
    cookie = old.create()
    assert json.loads(path.read_text()) == {cookie.split(".")[0]: int(cookie.split(".")[1])}
    assert Sessions(b"k" * 32, 180, path).valid(cookie)
