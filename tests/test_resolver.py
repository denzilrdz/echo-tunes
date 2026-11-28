"""The real Resolver, with threads standing in for the yt-dlp worker processes."""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from echo_tunes.music import extract, resolver
from echo_tunes.music.resolver import Resolver


def _fake_resolve(video_id: str, cookies: str | None, cache_dir: str | None) -> dict[str, Any]:
    if video_id.startswith("stuck"):
        time.sleep(1.0)
    elif video_id.startswith("slow"):
        time.sleep(0.2)
    elif video_id.startswith("bad"):
        raise RuntimeError("video unavailable")
    return {
        "url": f"https://cdn.test/{video_id}",
        "headers": {},
        "size": 10,
        "mime": "audio/mp4",
        "expires": int(time.time()) + 3600,
    }


@pytest.fixture
def res(monkeypatch: pytest.MonkeyPatch) -> Resolver:
    calls: list[str] = []
    lock = threading.Lock()

    def counted(video_id: str, *a: Any) -> dict[str, Any]:
        with lock:
            calls.append(video_id)
        return _fake_resolve(video_id, *a)

    monkeypatch.setattr(extract, "resolve", counted)
    monkeypatch.setattr(
        Resolver, "_new_pool", lambda self: ThreadPoolExecutor(max_workers=self._workers)
    )
    r = Resolver(workers=1, tasks_per_worker=10, cookies=None, cache_dir=None)
    r.calls = calls  # type: ignore[attr-defined]
    return r


async def test_concurrent_callers_share_one_lookup_and_cache_it(res: Resolver) -> None:
    a, b = await asyncio.gather(res.get("slow0000001"), res.get("slow0000001"))
    assert a is b
    assert await res.get("slow0000001") is a
    assert res.calls == ["slow0000001"]  # type: ignore[attr-defined]


async def test_a_cancelled_caller_does_not_fail_the_others(res: Resolver) -> None:
    first = asyncio.create_task(res.get("slow0000002"))
    await asyncio.sleep(0.01)
    second = asyncio.create_task(res.get("slow0000002"))
    await asyncio.sleep(0.01)
    first.cancel()
    src = await second
    assert src.url.endswith("slow0000002")
    with pytest.raises(asyncio.CancelledError):
        await first


async def test_one_timeout_does_not_fail_other_lookups(
    res: Resolver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(resolver, "RESOLVE_TIMEOUT", 0.3)
    stuck = asyncio.create_task(res.get("stuck000001"))
    await asyncio.sleep(0.05)
    waiting = asyncio.create_task(res.get("fine0000001"))  # queued behind the stuck one
    with pytest.raises(TimeoutError):
        await stuck
    src = await waiting  # retried on the new pool
    assert src.url.endswith("fine0000001")
    res.close()


async def test_waiting_for_a_worker_does_not_count_as_a_timeout(
    res: Resolver, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit: the timeout started when a lookup was queued, so with one worker, 4 of 6
    one-second lookups "timed out" while waiting their turn and the pool was restarted."""
    monkeypatch.setattr(resolver, "RESOLVE_TIMEOUT", 0.5)
    ids = [f"slow000000{i}" for i in range(6)]  # 0.2 s each, 1.2 s in a row on one worker
    results = await asyncio.gather(*(res.get(v) for v in ids))
    assert [r.url.rsplit("/", 1)[1] for r in results] == ids
    res.close()


async def test_errors_reach_every_caller_and_are_not_cached(res: Resolver) -> None:
    results = await asyncio.gather(
        res.get("bad00000001"), res.get("bad00000001"), return_exceptions=True
    )
    assert all(isinstance(e, RuntimeError) for e in results)
    with pytest.raises(RuntimeError):
        await res.get("bad00000001")
    assert res.calls.count("bad00000001") == 2  # type: ignore[attr-defined]


async def test_warm_then_invalidate(res: Resolver) -> None:
    res.warm("slow0000003")
    res.warm("slow0000003")  # already in flight: no second lookup
    await asyncio.sleep(0.4)
    assert res.calls == ["slow0000003"]  # type: ignore[attr-defined]
    res.invalidate("slow0000003")
    await res.get("slow0000003")
    assert res.calls == ["slow0000003", "slow0000003"]  # type: ignore[attr-defined]


async def test_search_runs_in_a_worker(res: Resolver, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_search(query: str, limit: int) -> list[dict[str, Any]]:
        return [{"id": "abcdefghijk", "title": query, "limit": limit}]

    monkeypatch.setattr(extract, "search", fake_search)
    assert await res.search("lofi", 3) == [{"id": "abcdefghijk", "title": "lofi", "limit": 3}]


async def test_a_stuck_search_times_out_and_frees_the_workers(
    res: Resolver, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stuck_search(query: str, limit: int) -> list[dict[str, Any]]:
        time.sleep(1.0)
        return []

    monkeypatch.setattr(extract, "search", stuck_search)
    monkeypatch.setattr(resolver, "SEARCH_TIMEOUT", 0.2)
    old_pool = res._pool
    with pytest.raises(TimeoutError):
        await res.search("anything", 5)
    assert res._pool is not old_pool  # the stuck worker's pool was replaced
    assert (await res.get("fine0000003")).url.endswith("fine0000003")
