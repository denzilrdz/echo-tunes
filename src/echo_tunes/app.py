"""HTTP endpoints: ``POST /alexa`` for the skill, ``GET /stream/…`` for audio, ``/healthz``."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from echo_tunes import __version__, tokens
from echo_tunes.alexa.skill import Skill, SkillConfig
from echo_tunes.alexa.verify import MAX_BODY_BYTES, AlexaVerifier, RequestRejected
from echo_tunes.checks import TEST_SONG, run_checks, summary
from echo_tunes.config import Settings
from echo_tunes.dashboard import DashboardDeps
from echo_tunes.health import memory_mb
from echo_tunes.history import History
from echo_tunes.metrics import METRICS
from echo_tunes.music import account
from echo_tunes.music.catalog import YTMusicCatalog
from echo_tunes.music.resolver import Resolver
from echo_tunes.player.store import StateStore
from echo_tunes.stream import MAX_STREAMS, AudioResponse, StreamError, StreamRelay

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Services:
    skill: Skill
    verifier: AlexaVerifier
    relay: StreamRelay
    stream_secret: bytes
    dashboard: DashboardDeps | None = None


def build_services(settings: Settings) -> tuple[Services, list[object]]:
    """Create the real services; also returns things that must be closed on shutdown."""
    resolver = Resolver(
        workers=settings.resolver_workers,
        tasks_per_worker=settings.resolver_tasks_per_worker,
        cookies=settings.ytdlp_cookies,
        cache_dir=settings.data_dir / "yt-dlp-cache",
    )
    store = StateStore(settings.data_dir / "players.sqlite3")
    history = History(settings.data_dir / "history.sqlite3", settings.history_days)
    # Song bodies get one connection per open stream (capped by StreamSlots); the readiness
    # probes that start each song have their own small pool so open streams can't block them.
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=5.0),
        limits=httpx.Limits(max_connections=MAX_STREAMS, max_keepalive_connections=4),
        follow_redirects=True,
    )
    probe_client = httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=5.0),
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=2),
        follow_redirects=True,
    )
    catalog = YTMusicCatalog(
        *account.make_client(
            settings.data_dir,
            settings.language,
            settings.location,
            account.load_client(
                settings.data_dir, settings.google_client_id, settings.google_client_secret
            ),
        ),
        send_history=settings.send_history,
    )
    skill = Skill(
        SkillConfig(
            base_url=settings.base_url,
            stream_secret=settings.stream_secret,
            stream_ttl_seconds=settings.stream_link_ttl_hours * 3600,
            radio_length=settings.radio_length,
            max_queue=settings.max_queue,
        ),
        catalog=catalog,
        resolver=resolver,
        store=store,
        history=history,
    )
    _register_gauges(store, history, lambda: catalog.signed_in)
    password = (
        settings.dashboard_password.get_secret_value() if settings.dashboard_password else None
    )
    relay = StreamRelay(resolver, client, probe_client)
    services = Services(
        skill=skill,
        verifier=AlexaVerifier(settings.skill_ids),
        relay=relay,
        stream_secret=settings.stream_secret,
        dashboard=DashboardDeps(
            store=store,
            history=history,
            signed_in=lambda: catalog.signed_in,
            device_names=settings.device_names,
            password=password or None,
            public_origin=settings.base_url,
            allowed_hosts=frozenset(
                [*settings.dashboard_hosts, (settings.public_url.host or "").lower()]
            ),
            run_checks=lambda: _setup_checks(settings, catalog, resolver, password),
            test_play=lambda: _test_play(skill),
            catalog=catalog,
            skill=skill,
            cut_stream=relay.slots.cut,
            experimental_skip=settings.experimental_skip,
            location=settings.location,
        ),
    )
    return services, [resolver, store, history, client, probe_client, services.verifier, catalog]


async def _setup_checks(
    settings: Settings, catalog: YTMusicCatalog, resolver: Resolver, password: str | None
) -> dict[str, Any]:
    async def resolve(video_id: str) -> tuple[str, dict[str, str]]:
        src = await resolver.get(video_id)
        return src.url, src.headers

    checks = await run_checks(
        settings,
        search=catalog.search_song,
        resolve=resolve,
        signed_in=catalog.signed_in,
        last_alexa=METRICS.last_alexa_at,
        password_set=bool(password),
        library=catalog.liked_songs,
    )
    return summary(checks)


def _test_play(skill: Skill) -> dict[str, Any]:
    """A 10-minute link to a test song, played by the browser through the public address."""
    return {
        "url": skill.stream_url(TEST_SONG, ttl_seconds=600),
        "title": "Never Gonna Give You Up",
        "artist": "Rick Astley",
        "note": "Plays through YouTube, this server and your public address, like an Echo would.",
    }


def _register_gauges(store: StateStore, history: History, signed_in: Callable[[], bool]) -> None:
    def playing() -> float:
        now = time.time()
        return sum(1 for _, st, up in store.all() if st.playing and now - up < 6 * 3600)

    METRICS.add_gauge("echo_tunes_echos_known", "Echos with a saved queue", store.count)
    METRICS.add_gauge("echo_tunes_echos_playing", "Echos playing right now", playing)
    METRICS.add_gauge("echo_tunes_history_plays", "Plays kept in the history", history.count)
    METRICS.add_gauge(
        "echo_tunes_history_retention_days", "Days of history kept", lambda: history.days
    )
    METRICS.add_gauge(
        "echo_tunes_youtube_music_signed_in", "1 if signed in to YouTube Music",
        lambda: 1.0 if signed_in() else 0.0,
    )  # fmt: skip


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    closers: list[object] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal services
        if services is None:
            services, made = build_services(settings or Settings())  # type: ignore[call-arg]
            closers.extend(made)
        app.state.services = services
        log.info("echo-tunes %s ready", __version__)
        yield
        for item in closers:
            close = getattr(item, "aclose", None) or getattr(item, "close", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result

    app = FastAPI(
        title="echo-tunes",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def svc(request: Request) -> Services:
        return request.app.state.services  # type: ignore[no-any-return]

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"name": "echo-tunes", "status": "running"}

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        # Public: no version number (the private dashboard's /api/health has it).
        return {"status": "ok", "memory_mb": memory_mb()}

    @app.post("/alexa")
    async def alexa(request: Request) -> Response:
        declared = request.headers.get("content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
            METRICS.alexa_rejected.labels("too_large").inc()
            return JSONResponse({"error": "bad request"}, status_code=400)
        # Read in pieces and stop at the limit: a chunked request has no Content-Length,
        # and the header can't be trusted anyway.
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_BODY_BYTES:
                METRICS.alexa_rejected.labels("too_large").inc()
                return JSONResponse({"error": "bad request"}, status_code=400)
        s = svc(request)
        try:
            envelope = await s.verifier.verify_async(dict(request.headers), bytes(body))
        except RequestRejected as exc:
            log.warning("rejected a request to /alexa: %s", exc)
            METRICS.alexa_rejected.labels(exc.reason).inc()
            return JSONResponse({"error": "bad request"}, status_code=400)
        METRICS.alexa_request(str((envelope.get("request") or {}).get("type", "")))
        return JSONResponse(await s.skill.handle(envelope))

    @app.api_route("/stream/{token}.m4a", methods=["GET", "HEAD"])
    async def stream(token: str, request: Request) -> Response:
        s = svc(request)
        try:
            video_id = tokens.check(s.stream_secret, token)
        except tokens.BadToken:
            METRICS.streams.labels("bad_link").inc()
            return Response(status_code=404)
        refused = s.relay.slots.acquire(token)
        if refused == "cut":
            METRICS.streams.labels("cut").inc()
            return Response(status_code=410)
        if refused:
            METRICS.streams.labels("too_many").inc()
            log.warning("refused a stream for %s: %s", video_id, refused)
            status = 503 if refused == "busy" else 429
            return Response(status_code=status, headers={"Retry-After": "5"})
        try:
            source, rng = await s.relay.open(video_id, request.headers.get("range"))
        except StreamError as exc:
            s.relay.slots.release(token)
            log.warning("stream %s: %s", video_id, exc)
            METRICS.streams.labels("range_error" if exc.status == 416 else "youtube_error").inc()
            headers = {"Content-Range": "bytes */*"} if exc.status == 416 else None
            return Response(status_code=exc.status, headers=headers)
        except BaseException as exc:
            s.relay.slots.release(token)
            if not isinstance(exc, Exception):
                raise
            log.exception("could not open stream for %s", video_id)
            METRICS.streams.labels("error").inc()
            return Response(status_code=502)
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(rng.length),
            "Cache-Control": "no-store",
        }
        status = 200
        if rng.partial:
            status = 206
            headers["Content-Range"] = f"bytes {rng.start}-{rng.end}/{rng.total}"
        if request.method == "HEAD":
            s.relay.slots.release(token)
            METRICS.streams.labels("ok").inc()
            return Response(status_code=status, headers=headers, media_type=source.mime)
        return AudioResponse(
            s.relay.body(source, rng, video_id),
            length=rng.length,
            on_close=lambda: s.relay.slots.release(token),
            abort=s.relay.slots.abort_event(token),
            status_code=status,
            headers=headers,
            media_type=source.mime,
        )

    return app
