"""Finds the audio link for a song, with a bounded cache and recycled worker processes."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from echo_tunes.cache import BoundedTTLCache
from echo_tunes.music import extract

log = logging.getLogger(__name__)

RESOLVE_TIMEOUT = 30.0
# Re-resolve a link this long before YouTube says it expires.
EXPIRY_MARGIN = 600


@dataclass(frozen=True, slots=True)
class AudioSource:
    url: str
    headers: dict[str, str]
    size: int | None
    mime: str
    expires: int
    resolved_at: float = field(default_factory=time.monotonic)


class AudioResolver(Protocol):
    async def get(self, video_id: str) -> AudioSource: ...
    def warm(self, video_id: str) -> None: ...
    def invalidate(self, video_id: str) -> None: ...


class Resolver:
    def __init__(
        self,
        workers: int,
        tasks_per_worker: int,
        cookies: Path | None,
        cache_dir: Path | None,
        cache_size: int = 64,
    ) -> None:
        # "spawn" gives each worker a clean interpreter; max_tasks_per_child recycles it.
        self._pool = ProcessPoolExecutor(
            max_workers=workers,
            mp_context=multiprocessing.get_context("spawn"),
            max_tasks_per_child=tasks_per_worker,
        )
        self._cookies = str(cookies) if cookies else None
        self._cache_dir = str(cache_dir) if cache_dir else None
        self._cache: BoundedTTLCache[str, AudioSource] = BoundedTTLCache(cache_size, ttl=3600)
        self._inflight: dict[str, asyncio.Future[AudioSource]] = {}
        self._background: set[asyncio.Task[None]] = set()

    async def get(self, video_id: str) -> AudioSource:
        cached = self._cache.get(video_id)
        if cached is not None:
            return cached
        pending = self._inflight.get(video_id)
        if pending is not None:
            return await asyncio.shield(pending)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[AudioSource] = loop.create_future()
        self._inflight[video_id] = future
        try:
            raw = await asyncio.wait_for(
                loop.run_in_executor(
                    self._pool, extract.resolve, video_id, self._cookies, self._cache_dir
                ),
                RESOLVE_TIMEOUT,
            )
            source = AudioSource(
                url=raw["url"],
                headers=raw["headers"],
                size=raw["size"],
                mime=raw["mime"],
                expires=raw["expires"],
            )
            ttl = max(60.0, source.expires - time.time() - EXPIRY_MARGIN)
            self._cache.set(video_id, source, ttl=ttl)
            future.set_result(source)
            return source
        except BaseException as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved so asyncio doesn't warn when nobody else waits
            raise
        finally:
            self._inflight.pop(video_id, None)

    def warm(self, video_id: str) -> None:
        """Resolve in the background so the link is ready before the Echo asks for it."""
        if video_id in self._cache or video_id in self._inflight:
            return
        task = asyncio.create_task(self._warm(video_id))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _warm(self, video_id: str) -> None:
        try:
            await self.get(video_id)
        except Exception as exc:
            log.warning("pre-loading %s failed: %s", video_id, exc)

    def invalidate(self, video_id: str) -> None:
        self._cache.pop(video_id)

    def close(self) -> None:
        for task in self._background:
            task.cancel()
        self._pool.shutdown(wait=False, cancel_futures=True)
