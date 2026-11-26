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
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from echo_tunes.music.resolver import AudioResolver, AudioSource

log = logging.getLogger(__name__)

CHUNK = 64 * 1024  # bytes handed to the Echo at a time
UPSTREAM_SPAN = 8 * 1024 * 1024  # bytes asked of YouTube per request (it throttles huge ranges)
WARMUP_SECONDS = 8.0  # how long a fresh YouTube link may answer 403 before it works
RETRY_EVERY = 0.3
MAX_RETRIES = 3  # network errors tolerated per song before giving up


class StreamError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


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
    """Interpret a client Range header against a file of ``total`` bytes (single range only)."""
    if not header:
        return ByteRange(0, total - 1, total, partial=False)
    unit, _, spec = header.partition("=")
    if unit.strip().lower() != "bytes" or "," in spec:
        raise StreamError(416, "unsupported range")
    first, _, last = spec.strip().partition("-")
    try:
        if first == "":  # suffix range: last N bytes
            n = int(last)
            if n <= 0:
                raise StreamError(416, "bad range")
            start, end = max(0, total - n), total - 1
        else:
            start = int(first)
            end = int(last) if last else total - 1
    except ValueError as exc:
        raise StreamError(416, "bad range") from exc
    end = min(end, total - 1)
    if start < 0 or start > end:
        raise StreamError(416, "range not satisfiable")
    return ByteRange(start, end, total, partial=True)


class StreamRelay:
    def __init__(self, resolver: AudioResolver, client: httpx.AsyncClient) -> None:
        self._resolver = resolver
        self._client = client

    async def open(self, video_id: str, range_header: str | None) -> tuple[AudioSource, ByteRange]:
        """Resolve the song and make sure YouTube will serve it, before sending any headers."""
        source = await self._resolver.get(video_id)
        if source.size is None:
            source = await self._learn_size(video_id, source)
        assert source.size is not None
        rng = parse_range(range_header, source.size)
        await self._wait_until_ready(video_id, source)
        return source, rng

    async def body(self, source: AudioSource, rng: ByteRange) -> AsyncIterator[bytes]:
        """Yield the requested bytes, fetching from YouTube in bounded spans."""
        pos = rng.start
        retries = 0
        while pos <= rng.end:
            span_end = min(rng.end, pos + UPSTREAM_SPAN - 1)
            headers = {**source.headers, "Range": f"bytes={pos}-{span_end}"}
            try:
                async with self._client.stream("GET", source.url, headers=headers) as resp:
                    if resp.status_code != 206:  # a 200 would be the whole file, not our range
                        log.warning("YouTube answered %s mid-stream", resp.status_code)
                        return
                    async for chunk in resp.aiter_bytes(CHUNK):
                        chunk = chunk[: span_end - pos + 1]  # never send more than asked for
                        if chunk:
                            yield chunk
                            pos += len(chunk)
            except httpx.TransportError as exc:
                # A network blip: carry on from the exact byte we reached.
                retries += 1
                if retries > MAX_RETRIES:
                    log.warning("giving up on the stream at byte %d: %r", pos, exc)
                    return
                await asyncio.sleep(RETRY_EVERY * retries)
                continue
            if pos <= span_end:  # upstream ended early
                log.warning("YouTube closed the stream early at byte %d", pos)
                return

    async def _probe(self, source: AudioSource) -> httpx.Response:
        headers = {**source.headers, "Range": "bytes=0-0"}
        async with self._client.stream("GET", source.url, headers=headers) as resp:
            return resp  # body (1 byte) is discarded when the context closes

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
