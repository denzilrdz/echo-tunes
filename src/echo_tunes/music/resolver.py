"""Finds the audio link for a song, with a bounded cache and recycled worker processes."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from echo_tunes.cache import BoundedTTLCache
from echo_tunes.metrics import METRICS
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
        self._workers, self._tasks_per_worker = workers, tasks_per_worker
        self._pool = self._new_pool()
        self._cookies = str(cookies) if cookies else None
        self._cache_dir = str(cache_dir) if cache_dir else None
        self._cache: BoundedTTLCache[str, AudioSource] = BoundedTTLCache(cache_size, ttl=3600)
        self._inflight: dict[str, asyncio.Task[AudioSource]] = {}
        self._background: set[asyncio.Task[None]] = set()
        # One lookup per worker at a time: the rest wait here, not in the pool's queue, so
        # RESOLVE_TIMEOUT only counts time actually spent running (waiting isn't "stuck").
        self._slots = asyncio.Semaphore(workers)

    async def get(self, video_id: str) -> AudioSource:
        cached = self._cache.get(video_id)
        if cached is not None:
            return cached
        task = self._inflight.get(video_id)
        if task is None:
            # The lookup runs as its own task: a caller that gives up (the Echo hung up) doesn't
            # cancel it for everyone else waiting on the same song, and the result is cached.
            task = asyncio.create_task(self._resolve(video_id))
            self._inflight[video_id] = task
            task.add_done_callback(lambda done: self._finished(video_id, done))
        return await asyncio.shield(task)

    async def _resolve(self, video_id: str) -> AudioSource:
        loop = asyncio.get_running_loop()
        t0 = time.monotonic()
        for attempt in range(2):
            try:
                async with self._slots:
                    pool = self._pool
                    raw = await asyncio.wait_for(
                        loop.run_in_executor(
                            pool, extract.resolve, video_id, self._cookies, self._cache_dir
                        ),
                        RESOLVE_TIMEOUT,
                    )
                break
            except TimeoutError as exc:
                # The worker is still stuck on this job; replace the pool so new songs
                # don't queue behind it.
                self._restart_pool(pool)
                METRICS.resolve_failed(exc)
                raise
            except (BrokenProcessPool, asyncio.CancelledError) as exc:
                # Another lookup timed out and the pool it shared with us was replaced.
                # That isn't this song's fault: try once more on the new pool.
                me = asyncio.current_task()
                if attempt == 0 and self._pool is not pool and not (me and me.cancelling()):
                    log.info("retrying %s on the restarted worker processes", video_id)
                    continue
                if isinstance(exc, BrokenProcessPool):
                    METRICS.resolve_failed(exc)
                raise
            except Exception as exc:
                METRICS.resolve_failed(exc)
                raise
        source = AudioSource(
            url=raw["url"],
            headers=raw["headers"],
            size=raw["size"],
            mime=raw["mime"],
            expires=raw["expires"],
        )
        ttl = max(60.0, source.expires - time.time() - EXPIRY_MARGIN)
        self._cache.set(video_id, source, ttl=ttl)
        METRICS.resolved(time.monotonic() - t0)
        return source

    def _finished(self, video_id: str, task: asyncio.Task[AudioSource]) -> None:
        self._inflight.pop(video_id, None)
        if not task.cancelled():
            task.exception()  # mark it retrieved: every caller may have given up already

    def _new_pool(self) -> ProcessPoolExecutor:
        # "spawn" gives each worker a clean interpreter; max_tasks_per_child recycles it.
        return ProcessPoolExecutor(
            max_workers=self._workers,
            mp_context=multiprocessing.get_context("spawn"),
            max_tasks_per_child=self._tasks_per_worker,
        )

    def _restart_pool(self, old: ProcessPoolExecutor) -> None:
        if old is not self._pool:
            return  # already replaced by another timed-out lookup
        self._pool = self._new_pool()
        log.warning("a YouTube lookup timed out; restarting the worker processes")
        for proc in list(getattr(old, "_processes", {}).values()):
            proc.terminate()
        old.shutdown(wait=False, cancel_futures=True)

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
        for task in [*self._background, *self._inflight.values()]:
            task.cancel()
        self._pool.shutdown(wait=False, cancel_futures=True)
