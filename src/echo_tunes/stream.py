"""Relays audio from YouTube to the Echo.

The Echo needs a stable HTTPS link on port 443, but YouTube's links are short-lived, tied to this
server's IP and only start working a couple of seconds after they are issued. So the Echo gets a
signed link to this server, and the bytes are passed through in small chunks: a song is never
held in memory, and when the Echo disconnects the upstream download stops too.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from echo_tunes.cache import BoundedTTLCache
from echo_tunes.metrics import METRICS
from echo_tunes.music.resolver import AudioResolver, AudioSource

log = logging.getLogger(__name__)

CHUNK = 64 * 1024  # bytes handed to the Echo at a time
UPSTREAM_SPAN = 8 * 1024 * 1024  # bytes asked of YouTube per request (it throttles huge ranges)
WARMUP_SECONDS = 8.0  # how long a fresh YouTube link may answer 403 before it works
RETRY_EVERY = 0.3
MAX_RETRIES = 3  # network errors in a row tolerated before giving up
SEND_TIMEOUT = 30.0  # a client that reads nothing for this long is dropped
# A client that reads, but only a trickle, would hold its slot for the whole song: after a
# grace period, each RATE_WINDOW must move at least MIN_RATE bytes per second on average.
# Lenient: an Echo reads in bursts and at least at the song's bitrate (128 kbps = 16 KB/s).
RATE_GRACE = 30.0
RATE_WINDOW = 60.0
MIN_RATE = 4 * 1024
MAX_STREAMS = 24  # open audio streams in total (each holds one connection to YouTube)
MAX_STREAMS_PER_LINK = 3  # an Echo opens one or two per song; more is someone else


class StreamSlots:
    """Caps open streams in total and per stream link, so one leaked link can't use them all."""

    def __init__(self, total: int = MAX_STREAMS, per_link: int = MAX_STREAMS_PER_LINK) -> None:
        self.total, self.per_link = total, per_link
        self._open: dict[str, int] = {}
        self.count = 0
        # Songs whose streams were cut on purpose ("skip now"): refused for a short while so
        # the Echo gives up on them instead of resuming with a Range request.
        self._cut: BoundedTTLCache[str, bool] = BoundedTTLCache(64, ttl=30)
        self._abort: dict[str, asyncio.Event] = {}

    def acquire(self, key: str) -> str | None:
        """None if a slot was taken, else why not ("busy" or "link")."""
        if self.count >= self.total:
            return "busy"
        if self._open.get(key, 0) >= self.per_link:
            return "link"
        if self._cut.get(key.split(".", 1)[0]):
            return "cut"
        self._open[key] = self._open.get(key, 0) + 1
        self._abort.setdefault(key, asyncio.Event())
        self.count += 1
        return None

    def abort_event(self, key: str) -> asyncio.Event:
        return self._abort.setdefault(key, asyncio.Event())

    def cut(self, video_id: str) -> int:
        """Stop every open stream of this song and refuse new ones for a while."""
        self._cut.set(video_id, True)
        hit = 0
        for key, event in self._abort.items():
            if key.split(".", 1)[0] == video_id:
                event.set()
                hit += 1
        return hit

    def release(self, key: str) -> None:
        n = self._open.get(key, 0) - 1
        if n > 0:
            self._open[key] = n
        else:
            self._open.pop(key, None)
            self._abort.pop(key, None)
        self.count = max(0, self.count - 1)


class AudioResponse(StreamingResponse):
    """A streaming response that drops clients which stop reading, and never sends a short body.

    uvicorn has no write timeout: a client that opens a stream and never reads would hold its
    YouTube connection forever. And when YouTube ends a song early, finishing the response
    would contradict the Content-Length already sent; leaving it unfinished makes the server
    close the connection, which the Echo treats as a network error and retries with a Range.
    """

    def __init__(
        self,
        content: AsyncIterator[bytes],
        *,
        length: int,
        on_close: Callable[[], None],
        abort: asyncio.Event | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(content, **kwargs)  # type: ignore[arg-type]
        self._length = length
        self._abort = abort
        self._on_close = on_close
        self.outcome = "ok"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._on_close()
            METRICS.streams.labels(self.outcome).inc()

    async def stream_response(self, send: Send) -> None:
        await send(
            {"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers}
        )
        sent = 0
        body = self.body_iterator
        started = time.monotonic()
        window_at, window_sent = started + RATE_GRACE, 0  # the first window starts after grace
        try:
            async for chunk in body:
                if self._abort is not None and self._abort.is_set():
                    self.outcome = "cut"
                    return
                try:
                    await asyncio.wait_for(
                        send({"type": "http.response.body", "body": chunk, "more_body": True}),
                        SEND_TIMEOUT,
                    )
                except TimeoutError:
                    log.info("dropping a stream whose client stopped reading")
                    self.outcome = "client_stalled"
                    return
                sent += len(chunk)
                now = time.monotonic()
                if now >= window_at + RATE_WINDOW:
                    if (sent - window_sent) / (now - window_at) < MIN_RATE:
                        log.info("dropping a stream whose client reads too slowly")
                        self.outcome = "client_stalled"
                        return
                    window_at, window_sent = now, sent
                elif now < window_at:
                    window_sent = sent  # still in the grace period
        except (asyncio.CancelledError, OSError):
            self.outcome = "client_gone"
            raise
        finally:
            await body.aclose()  # type: ignore[attr-defined]
        if sent < self._length:
            self.outcome = "cut_short"
            return  # unfinished on purpose (see the class docstring)
        await send({"type": "http.response.body", "body": b"", "more_body": False})


class StreamError(Exception):
    def __init__(self, status: int, message: str, total: int | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.total = total  # the file's size, for a 416's Content-Range


@dataclass(frozen=True, slots=True)
class ByteRange:
    start: int
    end: int  # inclusive
    total: int
    partial: bool

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def parse_range(header: str | None, total: int) -> ByteRange:
    """Interpret a client Range header against a file of ``total`` bytes (RFC 9110 §14).

    Anything we don't understand (another unit, several ranges, bad syntax, last < first) is
    ignored and the whole file is sent, as the RFC asks; only a well-formed range that misses
    the file entirely is a 416.
    """
    whole = ByteRange(0, total - 1, total, partial=False)
    if not header:
        return whole
    unit, sep, spec = header.partition("=")
    spec = spec.strip()
    if not sep or unit.strip().lower() != "bytes" or "," in spec:
        return whole
    first, dash, last = spec.partition("-")
    first, last = first.strip(), last.strip()
    if not dash or not (first or last):
        return whole
    if not (first.isascii() and last.isascii()):
        return whole
    if (first and not first.isdigit()) or (last and not last.isdigit()):
        return whole
    if not first:  # suffix range: the last N bytes
        n = int(last)
        if n == 0 or total == 0:
            raise StreamError(416, "range not satisfiable", total)
        return ByteRange(max(0, total - n), total - 1, total, partial=True)
    start = int(first)
    if last and int(last) < start:
        return whole  # invalid, so ignored
    if start >= total:
        raise StreamError(416, "range not satisfiable", total)
    end = min(int(last) if last else total - 1, total - 1)
    return ByteRange(start, end, total, partial=True)


class StreamRelay:
    def __init__(
        self,
        resolver: AudioResolver,
        client: httpx.AsyncClient,
        probe_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._resolver = resolver
        self._client = client  # song bodies: one connection per open stream
        # Readiness and size probes use their own pool, so streams in progress can never
        # starve the start of a new song.
        self._probe_client = probe_client or client
        self.slots = StreamSlots()

    async def open(self, video_id: str, range_header: str | None) -> tuple[AudioSource, ByteRange]:
        """Resolve the song and make sure YouTube will serve it, before sending any headers."""
        source = await self._resolver.get(video_id)
        if source.size is None:
            source = await self._learn_size(video_id, source)
        assert source.size is not None
        rng = parse_range(range_header, source.size)
        await self._wait_until_ready(video_id, source)
        return source, rng

    async def body(
        self, source: AudioSource, rng: ByteRange, video_id: str = ""
    ) -> AsyncIterator[bytes]:
        """Yield the requested bytes, fetching from YouTube in bounded spans."""
        pos = rng.start
        retries = 0
        refreshed = False
        while pos <= rng.end:
            span_end = min(rng.end, pos + UPSTREAM_SPAN - 1)
            headers = {**source.headers, "Range": f"bytes={pos}-{span_end}"}
            try:
                async with self._client.stream("GET", source.url, headers=headers) as resp:
                    if resp.status_code in (403, 410) and video_id and not refreshed:
                        # The link expired part-way through the song: get a new one once and
                        # carry on from the same byte (and stop caching the dead link).
                        refreshed = True
                        log.info("YouTube link for %s expired mid-song; refreshing", video_id)
                        self._resolver.invalidate(video_id)
                        source = await self._resolver.get(video_id)
                        await self._wait_until_ready(video_id, source)
                        continue
                    if resp.status_code != 206:  # a 200 would be the whole file, not our range
                        log.warning("YouTube answered %s mid-stream", resp.status_code)
                        if video_id:
                            self._resolver.invalidate(video_id)
                        return
                    async for chunk in resp.aiter_bytes(CHUNK):
                        chunk = chunk[: span_end - pos + 1]  # never send more than asked for
                        if chunk:
                            yield chunk
                            pos += len(chunk)
                            retries = 0  # the budget is for errors in a row
                            METRICS.stream_bytes.inc(len(chunk))
            except httpx.TransportError as exc:
                # A network blip: carry on from the exact byte we reached.
                retries += 1
                if retries > MAX_RETRIES:
                    log.warning("giving up on the stream at byte %d: %r", pos, exc)
                    return
                await asyncio.sleep(RETRY_EVERY * retries)
                continue
            except Exception as exc:  # the refresh failed (StreamError, a YouTube error)
                log.warning("could not refresh the link for %s: %s", video_id, exc)
                return
            if pos <= span_end:  # upstream ended early
                log.warning("YouTube closed the stream early at byte %d", pos)
                return

    async def _probe(self, source: AudioSource) -> httpx.Response:
        headers = {**source.headers, "Range": "bytes=0-0"}
        try:
            async with self._probe_client.stream("GET", source.url, headers=headers) as resp:
                return resp  # body (1 byte) is discarded when the context closes
        except httpx.TransportError as exc:
            # A network problem, not a bug: one log line (by the caller), not a traceback.
            raise StreamError(502, f"could not reach YouTube ({type(exc).__name__})") from exc

    async def _wait_until_ready(self, video_id: str, source: AudioSource) -> None:
        deadline = source.resolved_at + WARMUP_SECONDS
        while True:
            resp = await self._probe(source)
            if resp.status_code in (200, 206):
                return
            if resp.status_code != 403 or time.monotonic() >= deadline:
                self._resolver.invalidate(video_id)
                raise StreamError(502, f"YouTube refused the audio ({resp.status_code})")
            await asyncio.sleep(RETRY_EVERY)

    async def _learn_size(self, video_id: str, source: AudioSource) -> AudioSource:
        await self._wait_until_ready(video_id, source)
        resp = await self._probe(source)
        content_range = resp.headers.get("content-range", "")
        total = content_range.rpartition("/")[2]
        if not total.isdigit():
            raise StreamError(502, "YouTube did not report the file size")
        return AudioSource(
            url=source.url,
            headers=source.headers,
            size=int(total),
            mime=source.mime,
            expires=source.expires,
            resolved_at=source.resolved_at,
        )
