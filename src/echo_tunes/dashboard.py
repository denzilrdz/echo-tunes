"""The private dashboard: now playing, up next, history, stats, health and Prometheus metrics.

Served on its own port (``ECHO_TUNES_DASHBOARD_PORT``, default 8081), separate from the public
port that Amazon and the Echo use. Keep this port private: bind it to localhost or your LAN,
or publish it only inside your LAN or a VPN (WireGuard, Tailscale Serve, ...). An optional password
(``ECHO_TUNES_DASHBOARD_PASSWORD``, HTTP Basic, user ``admin``) adds a second lock.

Reading (now playing, history, browsing YouTube Music) works without a password on a private
network. Anything that changes something (play, queue, skip, clear history) is a POST that
needs the password to be set, a JSON body and a same-origin request.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import ipaddress
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic import Field as PydField

from echo_tunes import __version__
from echo_tunes.health import memory_mb
from echo_tunes.history import History
from echo_tunes.metrics import CONTENT_TYPE, METRICS
from echo_tunes.music import browse
from echo_tunes.music.catalog import NotSignedIn, Track
from echo_tunes.player.state import PlayerState
from echo_tunes.player.store import StateStore
from echo_tunes.tokens import is_video_id

ID_TAIL = 12  # characters of a device ID shown (and used for names)
STALE_AFTER = 6 * 3600  # an Echo silent this long is shown as idle


def csp(public_origin: str) -> str:
    media = f"'self' {public_origin}".strip()
    images = " ".join(f"https://{h}" for h in sorted(browse.IMAGE_HOSTS))
    return (
        f"default-src 'self'; img-src 'self' {images} data:; style-src 'self'; "
        f"script-src 'self'; connect-src 'self'; media-src {media}; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'none'"
    )


SETUP_CACHE_SECONDS = 60
SETUP_MIN_INTERVAL = 10


@dataclass(slots=True)
class DashboardDeps:
    store: StateStore
    history: History
    signed_in: Callable[[], bool]
    device_names: dict[str, str] = field(default_factory=dict)
    password: str | None = None
    session_days: int = 180  # 0 = until signed out
    public_origin: str = ""
    allowed_hosts: frozenset[str] = frozenset()  # beyond IPs, localhost and the public name
    # Setup page: run the checks, and give the browser a test stream link.
    run_checks: Callable[[], Awaitable[dict[str, Any]]] | None = None
    test_play: Callable[[], dict[str, Any]] | None = None
    # The player (all optional, so the dashboard also works without them in tests).
    catalog: Any = None  # YTMusicCatalog: search and browse
    skill: Any = None  # Skill: queue on an Echo, stream links for the browser
    cut_stream: Callable[[str], int] | None = None  # "skip now": cut a song's open streams
    experimental_skip: bool = False
    location: str = ""
    # Installable app (PWA): name, colour and an optional icon of your own.
    app_name: str = "echo-tunes"
    app_color: str = "#1f6feb"
    app_icon: Path | None = None


def host_allowed(host_header: str, extra: frozenset[str]) -> bool:
    """Only answer to IP addresses, localhost, or names we were told about.

    A DNS-rebinding attack points the attacker's own domain at this server, so its requests
    carry the attacker's name in Host; refusing unknown names blocks it.
    """
    host = host_header.strip().lower()
    if host.startswith("["):  # [IPv6] or [IPv6]:port, nothing else after the bracket
        inside, bracket, rest = host[1:].partition("]")
        if not bracket or (rest and not re.fullmatch(r":[0-9]{1,5}", rest)):
            return False
        host = inside
    elif host.count(":") == 1:
        host, _, port = host.partition(":")
        if not re.fullmatch(r"[0-9]{1,5}", port):
            return False
    if not host:
        return False
    if host in ("localhost", "localhost.") or host.endswith(".localhost") or host in extra:
        return True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def short_id(device: str) -> str:
    return device[-ID_TAIL:]


def _now_entry(
    device: str, st: PlayerState, updated: float, names: dict[str, str]
) -> dict[str, Any]:
    cur = st.current
    now = time.time()
    position = st.position_ms
    if st.playing and st.since:
        position += int((now - st.since) * 1000)
    if cur and cur.duration:
        position = min(position, cur.duration * 1000)
    up_next = st.tracks[st.index + 1 : st.index + 11] if cur else []
    sid = short_id(device)
    return {
        "id": sid,
        "name": names.get(sid, ""),
        "playing": bool(st.playing and cur and now - updated < STALE_AFTER),
        "position_ms": position,
        "updated": updated,
        "source": st.source_of(st.index) if cur else "",
        "shuffle": st.shuffle,
        "loop": st.loop,
        "queue_length": len(st.tracks),
        "queue_position": st.index + 1 if cur else 0,
        "current": _track(cur) if cur else None,
        "up_next": [_track(t) for t in up_next],
    }


def _track(t: Any) -> dict[str, Any]:
    return {"video_id": t.video_id, "title": t.title, "artist": t.artist, "duration": t.duration}


def health_report(history: History, signed_in: bool) -> dict[str, Any]:
    """Machine-friendly health, for Uptime Kuma's JSON query monitor and similar tools."""
    ok_at, err_at = METRICS.last_ok_at, METRICS.last_error_at
    now = time.time()
    youtube = "unknown"
    if ok_at or err_at:
        youtube = "ok" if ok_at >= err_at or now - err_at > 3600 else "failing"
    return {
        "status": "degraded" if youtube == "failing" else "ok",
        "version": __version__,
        "uptime_seconds": round(now - METRICS.started),
        "memory_mb": memory_mb(),
        "youtube": youtube,
        "last_audio_ok": ok_at or None,
        "last_audio_error": err_at or None,
        "last_error": METRICS.last_error_message if youtube == "failing" else "",
        "signed_in": signed_in,
        "history_days": history.days,
        "history_plays": history.count(),
    }


def create_dashboard(deps: DashboardDeps) -> FastAPI:
    app = FastAPI(
        title="echo-tunes dashboard", version=__version__, docs_url=None, redoc_url=None,
        openapi_url=None,
    )  # fmt: skip
    expected = (
        "Basic " + base64.b64encode(f"admin:{deps.password}".encode()).decode()
        if deps.password
        else None
    )
    # Password checks (sign-in page and Basic auth) take turns: each waits for the gate
    # *before* it is compared, and a wrong one holds the gate a second. So guesses run one at
    # a time, about one a second in total, however many are sent at once; when too many are
    # queued the rest are refused at once. Not per address: behind a reverse proxy every
    # client shares one, and one device could lock everyone out. Signed-in browsers (session
    # cookie) never touch the gate.
    gate = asyncio.Lock()
    queued = 0

    async def password_ok(given: str, wanted: str) -> bool | None:
        """True/False, or None when too many checks are already waiting."""
        nonlocal queued
        if queued >= MAX_QUEUED_CHECKS:
            return None
        queued += 1
        try:
            async with gate:
                if hmac.compare_digest(given.encode(), wanted.encode()):
                    return True
                await asyncio.sleep(WRONG_PASSWORD_DELAY)
                return False
        finally:
            queued -= 1

    def has_session(request: Request) -> bool:
        assert deps.password
        cookie = request.cookies.get(SESSION_COOKIE, "")
        return session_valid(deps.password, cookie, time.time())

    def signed_in(request: Request) -> bool:
        """For pages that only need to know (no password is checked here)."""
        return not deps.password or has_session(request)

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not host_allowed(request.headers.get("host", ""), deps.allowed_hosts):
            return Response("Unknown host name; add it to ECHO_TUNES_DASHBOARD_HOSTS.", 421)
        # Other websites may link here, but never read from here in the background.
        if (
            request.headers.get("sec-fetch-site") == "cross-site"
            and request.headers.get("sec-fetch-mode") != "navigate"
        ):
            return Response(status_code=403)
        if request.method not in ("GET", "HEAD"):
            refused = _write_refused(request)
            if refused:
                return JSONResponse({"detail": refused[1]}, status_code=refused[0])
        path = request.url.path
        allowed = not deps.password or _public(path) or has_session(request)
        basic = request.headers.get("authorization", "")
        if not allowed and basic and expected:
            ok = await password_ok(basic, expected)  # scripts and monitors (curl -u, Kuma)
            if ok is None:
                return JSONResponse({"detail": "busy, try again"}, status_code=429)
            allowed = ok
        if not allowed:
            if request.method == "GET" and path == "/":
                return RedirectResponse("/login", status_code=303)
            # Browsers get the login page instead of the Basic-auth pop-up; plain clients
            # (curl, monitors) are told to use Basic auth.
            browser = "sec-fetch-mode" in request.headers
            hdrs = {} if browser else {"WWW-Authenticate": 'Basic realm="echo-tunes"'}
            return JSONResponse({"detail": "sign in"}, status_code=401, headers=hdrs)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = policy
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/") or request.url.path == "/metrics":
            response.headers["Cache-Control"] = "no-store"
        return response

    policy = csp(deps.public_origin)
    setup_cache: dict[str, Any] = {"at": 0.0, "result": None}
    setup_lock = asyncio.Lock()
    web = resources.files("echo_tunes") / "web"
    name = html.escape(deps.app_name)
    index_html = (
        (web / "index.html")
        .read_text(encoding="utf-8")
        .replace("<title>echo-tunes</title>", f"<title>{name}</title>")
        .replace("<span>echo-tunes</span>", f"<span>{name}</span>")
        .replace(
            'content="#0d1117" data-theme-color', f'content="{deps.app_color}" data-theme-color'
        )
    )
    sw_js = (web / "sw.js").read_text(encoding="utf-8")

    login_html = (
        (web / "login.html")
        .read_text(encoding="utf-8")
        .replace("<title>echo-tunes</title>", f"<title>Sign in · {name}</title>")
        .replace("<span>echo-tunes</span>", f"<span>{name}</span>")
    )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Response:
        resp = HTMLResponse(index_html)
        if deps.password and deps.session_days == 0 and request.cookies.get(SESSION_COOKIE):
            set_session(resp, request)  # keep a never-expiring session's cookie fresh
        return resp

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> Response:
        if not deps.password or signed_in(request):
            return RedirectResponse("/", status_code=303)
        return HTMLResponse(login_html)

    @app.post("/api/login")
    async def login(body: _LoginIn, request: Request) -> Response:
        if not deps.password:
            raise HTTPException(404, "no password is set")
        ok = await password_ok(body.password, deps.password)
        if ok is None:
            raise HTTPException(429, "Too many sign-in attempts at once; try again shortly.")
        if not ok:
            raise HTTPException(401, "Wrong password.")
        resp = JSONResponse({"status": "ok"})
        set_session(resp, request)
        return resp

    def set_session(resp: Response, request: Request) -> None:
        assert deps.password
        days = deps.session_days
        expires = int(time.time()) + days * 86400 if days else 0  # 0 = never
        resp.set_cookie(
            SESSION_COOKIE,
            session_value(deps.password, expires),
            # Browsers keep a cookie at most ~400 days; with no expiry it's renewed on every
            # visit (see index()), so it never runs out while you use it.
            max_age=(days or COOKIE_MAX_DAYS) * 86400,
            httponly=True,
            samesite="lax",
            secure=_https(request),
            path="/",
        )

    @app.post("/api/logout")
    async def logout() -> Response:
        resp = JSONResponse({"status": "ok"})
        resp.delete_cookie(SESSION_COOKIE, path="/")
        return resp

    @app.get("/manifest.webmanifest")
    async def manifest() -> JSONResponse:
        if deps.app_icon:
            icons = [
                {
                    "src": "/app-icon.png",
                    "sizes": "any",
                    "type": "image/png",
                    "purpose": "any maskable",
                }
            ]
        else:
            icons = [
                {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
                {
                    "src": "/static/icon-maskable-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ]
        return JSONResponse(
            {
                "name": deps.app_name,
                "short_name": deps.app_name[:12],
                "description": "YouTube Music in your browser or on your Echo.",
                "id": "/",
                "start_url": "/#play",
                "scope": "/",
                "display": "standalone",
                "background_color": "#0d1117",
                "theme_color": deps.app_color,
                "icons": icons,
                "shortcuts": [
                    {"name": "Player", "url": "/#play"},
                    {"name": "Now playing", "url": "/#now"},
                    {"name": "History", "url": "/#history"},
                ],
            },
            media_type="application/manifest+json",
        )

    @app.get("/sw.js")
    async def service_worker() -> Response:
        # Served from the root so it may control the whole dashboard.
        return Response(sw_js, media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @app.get("/app-icon.png")
    async def app_icon() -> Response:
        if not deps.app_icon:
            return Response(status_code=404)
        return FileResponse(deps.app_icon, media_type="image/png")

    app.mount("/static", StaticFiles(directory=str(web)), name="static")

    @app.get("/api/now")
    async def now() -> dict[str, Any]:
        players = [
            _now_entry(d, st, up, deps.device_names)
            for d, st, up in deps.store.all()
            if st.current is not None
        ]
        players.sort(key=lambda p: (not p["playing"], -p["updated"]))  # playing Echos first
        return {"time": time.time(), "devices": players}

    @app.get("/api/history")
    async def history(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        device: str | None = Query(None, max_length=64),
        q: str | None = Query(None, max_length=100),
        days: int | None = Query(None, ge=1, le=3650),
    ) -> dict[str, Any]:
        full = _full_id(deps.store, device)
        rows = deps.history.recent(limit=limit, offset=offset, device=full, query=q, days=days)
        for row in rows:
            row["device"] = short_id(row["device"])
            row["device_name"] = deps.device_names.get(row["device"], "")
        return {"enabled": deps.history.enabled, "days": deps.history.days, "plays": rows}

    @app.get("/api/stats")
    async def stats(
        days: int | None = Query(None, ge=1, le=3650),
        device: str | None = Query(None, max_length=64),
        tz: int | None = Query(None, ge=-840, le=840, description="minutes east of UTC"),
    ) -> dict[str, Any]:
        return deps.history.stats(days, _full_id(deps.store, device), tz)

    @app.get("/api/devices")
    async def devices() -> list[dict[str, str]]:
        return [
            {"id": short_id(d), "name": deps.device_names.get(short_id(d), "")}
            for d, _, _ in deps.store.all()
        ]

    @app.get("/api/health")
    async def health() -> JSONResponse:
        report = health_report(deps.history, deps.signed_in())
        return JSONResponse(report, status_code=200 if report["status"] == "ok" else 503)

    @app.get("/api/setup")
    async def setup(refresh: bool = False) -> JSONResponse:
        if deps.run_checks is None:
            return JSONResponse({"error": "not available"}, status_code=404)
        async with setup_lock:  # one run at a time; reuse a recent result
            age = time.time() - setup_cache["at"]
            fresh = setup_cache["result"] is not None and (
                age < SETUP_MIN_INTERVAL or (age < SETUP_CACHE_SECONDS and not refresh)
            )
            if not fresh:
                setup_cache["result"] = await deps.run_checks()
                setup_cache["at"] = time.time()
        return JSONResponse(setup_cache["result"])

    @app.get("/api/test-play")
    async def test_play() -> JSONResponse:
        if deps.test_play is None:
            return JSONResponse({"error": "not available"}, status_code=404)
        return JSONResponse(deps.test_play())

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(METRICS.render(), media_type=CONTENT_TYPE)

    _player_routes(app, deps)
    return app


# --- the player -------------------------------------------------------------------------------
BROWSER_DEVICE = "dashboard-browser"  # history rows for songs played in a browser
MAX_TRACKS = 200


class _TrackIn(BaseModel):
    video_id: str = PydField(min_length=11, max_length=11)
    title: str = PydField(max_length=200)
    artist: str = PydField(default="", max_length=200)
    duration: int | None = PydField(default=None, ge=0, le=86400)

    def track(self) -> Track:
        if not is_video_id(self.video_id):
            raise HTTPException(422, "bad video ID")
        return Track(
            self.video_id, self.title.strip() or "Unknown", self.artist.strip(), self.duration
        )


class _QueueIn(BaseModel):
    device: str = PydField(min_length=1, max_length=64)
    mode: Literal["now", "next", "queue"]
    source: str = PydField(default="Dashboard", max_length=120)
    tracks: list[_TrackIn] = PydField(min_length=1, max_length=MAX_TRACKS)


class _DeviceIn(BaseModel):
    device: str = PydField(min_length=1, max_length=64)


class _VideoIn(BaseModel):
    video_id: str = PydField(min_length=11, max_length=11)


class _PlayedIn(BaseModel):
    track: _TrackIn
    source: str = PydField(default="Dashboard player", max_length=120)


def _player_routes(app: FastAPI, deps: DashboardDeps) -> None:
    def need(thing: Any) -> Any:
        if thing is None:
            raise HTTPException(404, "not available")
        return thing

    def action(request: Request) -> None:
        """Every state-changing call needs the password to be set (the middleware has checked
        it, and that the request is same-origin JSON: see _write_refused)."""
        if not deps.password:
            raise HTTPException(
                403,
                "Set ECHO_TUNES_DASHBOARD_PASSWORD to use the player and other actions.",
            )

    async def youtube(call: Awaitable[Any]) -> Any:
        try:
            return await call
        except NotSignedIn as exc:
            raise HTTPException(409, "Sign in to YouTube Music first: echo-tunes login") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            METRICS.youtube_errors.inc()
            raise HTTPException(502, "YouTube Music didn't answer; try again.") from exc

    def items(xs: list[browse.Item]) -> list[dict[str, Any]]:
        return [x.to_dict() for x in xs]

    def tracks(xs: list[Track]) -> list[dict[str, Any]]:
        return [_track(t) for t in xs]

    def full_device(short: str) -> str:
        full = _full_id(deps.store, short)
        if full is None or full.startswith("\x00"):
            raise HTTPException(404, "unknown Echo")
        return full

    @app.get("/api/player")
    async def player() -> dict[str, Any]:
        echos = []
        for device, st, updated in deps.store.all():
            if device == BROWSER_DEVICE:
                continue
            entry = _now_entry(device, st, updated, deps.device_names)
            keys = ("id", "name", "playing", "current", "updated", "position_ms")
            echos.append({k: entry[k] for k in keys})
        echos.sort(key=lambda e: (not e["playing"], -e["updated"]))
        return {
            "actions": bool(deps.password) and deps.skill is not None,
            "experimental_skip": deps.experimental_skip,
            "signed_in": deps.signed_in(),
            "echos": echos,
        }

    @app.get("/api/search")
    async def search(
        q: str = Query(min_length=1, max_length=100),
        kind: browse.Kind = "song",
    ) -> dict[str, Any]:
        found = await youtube(need(deps.catalog).search_items(q.strip(), kind))
        return {"kind": kind, "items": items(found)}

    @app.get("/api/browse/home")
    async def home() -> dict[str, Any]:
        rows = await youtube(need(deps.catalog).home())
        return {"sections": [{"title": s["title"], "items": items(s["items"])} for s in rows]}

    @app.get("/api/browse/explore")
    async def explore() -> dict[str, Any]:
        cat = need(deps.catalog)
        charts = await youtube(cat.charts(deps.location))
        moods = await youtube(cat.moods())
        return {
            "charts": items(charts["playlists"]),
            "artists": items(charts["artists"]),
            "moods": moods,
        }

    @app.get("/api/browse/mood")
    async def mood(params: str = Query(min_length=4, max_length=300)) -> dict[str, Any]:
        return {"items": items(await youtube(need(deps.catalog).mood_playlists(params)))}

    @app.get("/api/browse/library")
    async def library() -> dict[str, Any]:
        return {"items": items(await youtube(need(deps.catalog).library_playlists()))}

    @app.get("/api/browse/tracks")
    async def tracks_of(
        kind: browse.Kind, id: str = Query(min_length=2, max_length=80)
    ) -> dict[str, Any]:
        title, found = await youtube(need(deps.catalog).items_of(kind, id))
        return {"title": title, "tracks": tracks(found[:MAX_TRACKS])}

    @app.post("/api/play/stream-link")
    async def stream_link(body: _VideoIn, request: Request) -> dict[str, Any]:
        """A signed link for this browser to play a song through the public address."""
        action(request)
        if not is_video_id(body.video_id):
            raise HTTPException(422, "bad video ID")
        need(deps.skill).resolver.warm(body.video_id)
        return {"url": deps.skill.stream_url(body.video_id, ttl_seconds=3 * 3600)}

    @app.post("/api/play/played")
    async def played(body: _PlayedIn, request: Request) -> dict[str, str]:
        """The browser started a song: keep it in the history like an Echo's."""
        action(request)
        deps.history.started(BROWSER_DEVICE, body.track.track(), body.source)
        return {"status": "ok"}

    @app.post("/api/play/echo")
    async def queue_on_echo(body: _QueueIn, request: Request) -> dict[str, Any]:
        action(request)
        device = full_device(body.device)
        try:
            result: dict[str, Any] = await need(deps.skill).dashboard_queue(
                device, [t.track() for t in body.tracks], body.mode, body.source
            )
            return result
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/play/skip")
    async def skip(body: _DeviceIn, request: Request) -> dict[str, Any]:
        action(request)
        if not deps.experimental_skip or deps.cut_stream is None:
            raise HTTPException(403, "Turn on ECHO_TUNES_EXPERIMENTAL_SKIP to try this.")
        video = await need(deps.skill).dashboard_skip(full_device(body.device))
        if video is None:
            raise HTTPException(409, "Nothing is playing on this Echo.")
        cut = deps.cut_stream(video)
        return {
            "cut": cut,
            "note": "Skipping…"
            if cut
            else "The Echo already has the whole song; it can't be "
            "cut short. The next song is queued.",
        }

    @app.post("/api/history/clear")
    async def clear_history(request: Request) -> dict[str, int]:
        action(request)
        return {"removed": deps.history.clear()}


# --- signing in -----------------------------------------------------------------------------
SESSION_COOKIE = "echo_tunes_session"
COOKIE_MAX_DAYS = 400  # the longest browsers keep a cookie
WRONG_PASSWORD_DELAY = 1.0  # seconds a wrong password holds the gate
MAX_QUEUED_CHECKS = 20  # password checks allowed to wait; more get 429 at once


class _LoginIn(BaseModel):
    password: str = PydField(min_length=1, max_length=200)


def session_value(password: str, expires: int) -> str:
    """``<expiry>.<HMAC of it, keyed by the password>`` (expiry 0 = never): no server-side
    session store, and changing the password signs every device out."""
    sig = hmac.new(password.encode(), f"session:{expires}".encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def session_valid(password: str, value: str, now: float) -> bool:
    expires = value.partition(".")[0]
    if not expires.isascii() or not expires.isdigit() or len(expires) > 12:
        return False
    if expires != "0" and int(expires) < now:
        return False
    return hmac.compare_digest(value.encode(), session_value(password, int(expires)).encode())


def _public(path: str) -> bool:
    """What the login page and an app install need before signing in (no data in any of it)."""
    return path in ("/login", "/api/login", "/manifest.webmanifest", "/sw.js") or (
        path.startswith("/static/")
    )


def _https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto.split(",")[0].strip().lower() == "https"


def _write_refused(request: Request) -> tuple[int, str] | None:
    """Anything but GET must be JSON (a plain HTML form can't send it) from this dashboard's
    own page. Checked before the body is read."""
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        return 415, "JSON only"
    site = request.headers.get("sec-fetch-site")
    if site is not None and site not in ("same-origin", "none"):
        return 403, "cross-site request refused"
    origin = request.headers.get("origin")
    if origin and origin.split("://", 1)[-1].lower() != request.headers.get("host", "").lower():
        return 403, "cross-origin request refused"
    return None


def _full_id(store: StateStore, short: str | None) -> str | None:
    """The dashboard only shows ID tails; map one back to the stored device ID."""
    if not short:
        return None
    for device, _, _ in store.all():
        if short_id(device) == short:
            return device
    return "\x00no-such-device"
