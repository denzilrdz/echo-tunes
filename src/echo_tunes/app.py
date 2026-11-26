"""HTTP endpoints: ``POST /alexa`` for the skill, ``GET /stream/…`` for audio, ``/healthz``."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from echo_tunes import __version__, tokens
from echo_tunes.alexa.skill import Skill, SkillConfig
from echo_tunes.alexa.verify import MAX_BODY_BYTES, AlexaVerifier, RequestRejected
from echo_tunes.config import Settings
from echo_tunes.health import memory_mb
from echo_tunes.music.catalog import YTMusicCatalog
from echo_tunes.music.resolver import Resolver
from echo_tunes.player.store import StateStore
from echo_tunes.stream import StreamError, StreamRelay

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Services:
    skill: Skill
    verifier: AlexaVerifier
    relay: StreamRelay
    stream_secret: bytes


def build_services(settings: Settings) -> tuple[Services, list[object]]:
    """Create the real services; also returns things that must be closed on shutdown."""
    resolver = Resolver(
        workers=settings.resolver_workers,
        tasks_per_worker=settings.resolver_tasks_per_worker,
        cookies=settings.ytdlp_cookies,
        cache_dir=settings.data_dir / "yt-dlp-cache",
    )
    store = StateStore(settings.data_dir / "players.sqlite3")
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=5.0),
        limits=httpx.Limits(max_connections=16, max_keepalive_connections=4),
        follow_redirects=True,
    )
    skill = Skill(
        SkillConfig(
            base_url=settings.base_url,
            stream_secret=settings.stream_secret,
            stream_ttl_seconds=settings.stream_link_ttl_hours * 3600,
            radio_length=settings.radio_length,
            max_queue=settings.max_queue,
        ),
        catalog=YTMusicCatalog(settings.language, settings.location),
        resolver=resolver,
        store=store,
    )
    services = Services(
        skill=skill,
        verifier=AlexaVerifier(settings.skill_ids),
        relay=StreamRelay(resolver, client),
        stream_secret=settings.stream_secret,
    )
    return services, [resolver, store, client]


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
        return {"status": "ok", "version": __version__, "memory_mb": memory_mb()}

    @app.post("/alexa")
    async def alexa(request: Request) -> Response:
        declared = request.headers.get("content-length", "0")
        if not declared.isdigit() or int(declared) > MAX_BODY_BYTES:
            return JSONResponse({"error": "bad request"}, status_code=400)
        body = await request.body()
        s = svc(request)
        try:
            envelope = await asyncio.to_thread(s.verifier.verify, dict(request.headers), body)
        except RequestRejected as exc:
            log.warning("rejected a request to /alexa: %s", exc)
            return JSONResponse({"error": "bad request"}, status_code=400)
        return JSONResponse(await s.skill.handle(envelope))

    @app.api_route("/stream/{token}.m4a", methods=["GET", "HEAD"])
    async def stream(token: str, request: Request) -> Response:
        s = svc(request)
        try:
            video_id = tokens.check(s.stream_secret, token)
        except tokens.BadToken:
            return Response(status_code=404)
        try:
            source, rng = await s.relay.open(video_id, request.headers.get("range"))
        except StreamError as exc:
            log.warning("stream %s: %s", video_id, exc)
            headers = {"Content-Range": "bytes */*"} if exc.status == 416 else None
            return Response(status_code=exc.status, headers=headers)
        except Exception:
            log.exception("could not open stream for %s", video_id)
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
            return Response(status_code=status, headers=headers, media_type=source.mime)
        return StreamingResponse(
            s.relay.body(source, rng), status_code=status, headers=headers, media_type=source.mime
        )

    return app
