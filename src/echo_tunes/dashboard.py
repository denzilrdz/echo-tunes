"""The private dashboard: now playing, up next, history, stats, health and Prometheus metrics.

Served on its own port (``ECHO_TUNES_DASHBOARD_PORT``, default 8081), separate from the public
port that Amazon and the Echo use. Keep this port private: bind it to localhost or your LAN,
or publish it only inside your LAN or a VPN (WireGuard, Tailscale Serve, ...). An optional password
(``ECHO_TUNES_DASHBOARD_PASSWORD``, HTTP Basic, user ``admin``) adds a second lock.

Read-only: nothing here can change what plays.
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import ipaddress
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from echo_tunes import __version__
from echo_tunes.health import memory_mb
from echo_tunes.history import History
from echo_tunes.metrics import CONTENT_TYPE, METRICS
from echo_tunes.player.state import PlayerState
from echo_tunes.player.store import StateStore

ID_TAIL = 12  # characters of a device ID shown (and used for names)
STALE_AFTER = 6 * 3600  # an Echo silent this long is shown as idle


def csp(public_origin: str) -> str:
    media = f"'self' {public_origin}".strip()
    return (
        "default-src 'self'; img-src 'self' https://i.ytimg.com data:; style-src 'self'; "
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
    public_origin: str = ""
    allowed_hosts: frozenset[str] = frozenset()  # beyond IPs, localhost and the public name
    # Setup page: run the checks, and give the browser a test stream link.
    run_checks: Callable[[], Awaitable[dict[str, Any]]] | None = None
    test_play: Callable[[], dict[str, Any]] | None = None


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
        if expected and not hmac.compare_digest(
            request.headers.get("authorization", "").encode(), expected.encode()
        ):
            return Response(
                status_code=401, headers={"WWW-Authenticate": 'Basic realm="echo-tunes"'}
            )
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
    index_html = (web / "index.html").read_text(encoding="utf-8")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return index_html

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

    return app


def _full_id(store: StateStore, short: str | None) -> str | None:
    """The dashboard only shows ID tails; map one back to the stored device ID."""
    if not short:
        return None
    for device, _, _ in store.all():
        if short_id(device) == short:
            return device
    return "\x00no-such-device"
