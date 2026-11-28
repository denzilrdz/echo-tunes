"""Finds the audio link for a song, with a bounded cache and recycled worker processes.
The same workers also run YouTube searches (yt-dlp is only ever loaded in them)."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from echo_tunes.cache import BoundedTTLCache
from echo_tunes.metrics import METRICS
from echo_tunes.music import extract

log = logging.getLogger(__name__)

RESOLVE_TIMEOUT = 30.0
# A search runs while Alexa waits (~8 s for the whole answer).
SEARCH_TIMEOUT = 5.0
# Searches run one at a time, so with two or more workers a song's audio link never waits
# behind them; a few more may wait their turn, the rest are refused at once.
MAX_SEARCHES_WAITING = 4


class Busy(Exception):
    """Too many searches are already waiting; try again shortly."""


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
        self._searching = asyncio.Semaphore(1)
        self._search_queue = 0

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
        t0 = time.monotonic()
        try:
            raw = await self._run(
                RESOLVE_TIMEOUT, extract.resolve, video_id, self._cookies, self._cache_dir
            )
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

    async def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        """YouTube's search results, as plain data from a worker (see music/youtube.py)."""
        if self._search_queue >= MAX_SEARCHES_WAITING:
            raise Busy
        self._search_queue += 1
        try:
            async with self._searching:
                result: list[dict[str, Any]] = await self._run(
                    SEARCH_TIMEOUT, extract.search, query, limit
                )
                return result
        finally:
            self._search_queue -= 1

    async def _run(self, limit: float, fn: Callable[..., Any], *args: Any) -> Any:
        """Run ``fn`` in a worker. ``limit`` (seconds) counts only time spent running.

        The worker slot is held until the job really ends: a caller that gives up (a search
        past its budget, a dropped request) leaves the job running in its worker, and the slot
        must stay taken until then, or the next job would queue behind it in the pool with its
        own clock already running.
        """
        loop = asyncio.get_running_loop()
        for attempt in range(2):
            await self._slots.acquire()
            free = self._slot_releaser()
            pool = self._pool
            try:
                job = loop.run_in_executor(pool, fn, *args)
            except BaseException:
                free()
                raise
            try:
                return await asyncio.wait_for(asyncio.shield(job), limit)
            except TimeoutError:
                # The worker is still stuck on this job; replace the pool so new jobs
                # don't queue behind it. Its slot belongs to the new pool now.
                self._restart_pool(pool)
                free()
                raise
            except (BrokenProcessPool, asyncio.CancelledError):
                # Another job timed out and the pool it shared with us was replaced.
                # That isn't this job's fault: try once more on the new pool.
                me = asyncio.current_task()
                if attempt == 0 and self._pool is not pool and not (me and me.cancelling()):
                    log.info("retrying a job on the restarted worker processes")
                    continue
                raise
            finally:
                if job.done():
                    free()
                else:  # the caller gave up; the worker is still busy with it
                    job.add_done_callback(_release_when_done(free))
        raise AssertionError("unreachable")

    def _slot_releaser(self) -> Callable[[], None]:
        """Releases one worker slot, once, however many times it's called."""
        held = [True]

        def free() -> None:
            if held[0]:
                held[0] = False
                self._slots.release()

        return free

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
        log.warning("a YouTube job timed out; restarting the worker processes")
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


def _release_when_done(free: Callable[[], None]) -> Callable[[asyncio.Future[Any]], None]:
    """A done-callback that frees this job's own worker slot (bound now, not by loop name)."""
    return lambda _job: free()
