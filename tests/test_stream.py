from __future__ import annotations

import time

import httpx
import pytest

from echo_tunes import stream as stream_mod
from echo_tunes.music.resolver import AudioSource
from echo_tunes.stream import StreamError, StreamRelay, parse_range

AUDIO = bytes(range(256)) * 400  # 102,400 bytes of fake audio


class OneSource:
    def __init__(self, size: int | None = len(AUDIO), age: float = 60) -> None:
        self.size, self.age = size, age
        self.invalidated = 0

    async def get(self, video_id: str) -> AudioSource:
        return AudioSource(
            "https://cdn.test/a",
            {"User-Agent": "t"},
            self.size,
            "audio/mp4",
            int(time.time()) + 3600,
            resolved_at=time.monotonic() - self.age,
        )

    def warm(self, video_id: str) -> None: ...

    def invalidate(self, video_id: str) -> None:
        self.invalidated += 1


def cdn(forbidden_for: int = 0, log: list[str] | None = None) -> httpx.AsyncClient:
    """A fake YouTube CDN that answers 403 for the first N requests, then honours Range."""
    calls = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        calls[0] += 1
        if log is not None:
            log.append(req.headers.get("range", ""))
        if calls[0] <= forbidden_for:
            return httpx.Response(403)
        start, _, end = req.headers["range"].removeprefix("bytes=").partition("-")
        s, e = int(start), min(int(end or len(AUDIO) - 1), len(AUDIO) - 1)
        return httpx.Response(
            206, content=AUDIO[s : e + 1], headers={"content-range": f"bytes {s}-{e}/{len(AUDIO)}"}
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def collect(relay: StreamRelay, range_header: str | None) -> bytes:
    src, rng = await relay.open("dQw4w9WgXcQ", range_header)
    return b"".join([c async for c in relay.body(src, rng)])


@pytest.mark.parametrize(
    ("header", "start", "end", "partial"),
    [
        (None, 0, 999, False),
        ("bytes=0-", 0, 999, True),
        ("bytes=100-199", 100, 199, True),
        ("bytes=-100", 900, 999, True),
        ("bytes=900-5000", 900, 999, True),
    ],
)
def test_parse_range(header: str | None, start: int, end: int, partial: bool) -> None:
    r = parse_range(header, 1000)
    assert (r.start, r.end, r.partial) == (start, end, partial)


@pytest.mark.parametrize(
    "header", ["bytes=1000-", "bytes=5-1", "items=0-1", "bytes=0-1,5-6", "bytes=x-"]
)
def test_parse_range_rejects(header: str) -> None:
    with pytest.raises(StreamError):
        parse_range(header, 1000)


async def test_full_and_partial_stream() -> None:
    relay = StreamRelay(OneSource(), cdn())
    assert await collect(relay, None) == AUDIO
    assert await collect(relay, "bytes=1000-1999") == AUDIO[1000:2000]


async def test_large_ranges_are_split_into_bounded_upstream_requests(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(stream_mod, "UPSTREAM_SPAN", 30_000)
    log: list[str] = []
    relay = StreamRelay(OneSource(), cdn(log=log))
    assert await collect(relay, None) == AUDIO
    body_requests = [r for r in log if r != "bytes=0-0"]
    assert body_requests == [
        "bytes=0-29999",
        "bytes=30000-59999",
        "bytes=60000-89999",
        "bytes=90000-102399",
    ]


async def test_waits_out_youtube_warmup_403s(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(stream_mod, "RETRY_EVERY", 0.01)
    relay = StreamRelay(OneSource(age=0), cdn(forbidden_for=4))
    assert await collect(relay, "bytes=0-9") == AUDIO[:10]


async def test_gives_up_and_invalidates_after_warmup(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(stream_mod, "RETRY_EVERY", 0.01)
    monkeypatch.setattr(stream_mod, "WARMUP_SECONDS", 0.05)
    source = OneSource(age=0)
    relay = StreamRelay(source, cdn(forbidden_for=10_000))
    with pytest.raises(StreamError) as exc:
        await collect(relay, None)
    assert exc.value.status == 502 and source.invalidated == 1


async def test_learns_size_when_youtube_did_not_say() -> None:
    relay = StreamRelay(OneSource(size=None), cdn())
    src, rng = await relay.open("dQw4w9WgXcQ", None)
    assert src.size == len(AUDIO) and rng.length == len(AUDIO)


async def test_network_blip_resumes_from_same_byte(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(stream_mod, "RETRY_EVERY", 0.01)
    monkeypatch.setattr(stream_mod, "UPSTREAM_SPAN", 30_000)
    inner = cdn()
    seen: list[str] = []
    failed = [False]

    async def flaky(req: httpx.Request) -> httpx.Response:
        seen.append(req.headers.get("range", ""))
        if req.headers.get("range") == "bytes=30000-59999" and not failed[0]:
            failed[0] = True
            raise httpx.ConnectError("blip")
        return await inner._transport.handle_async_request(req)

    relay = StreamRelay(OneSource(), httpx.AsyncClient(transport=httpx.MockTransport(flaky)))
    assert await collect(relay, None) == AUDIO
    assert seen.count("bytes=30000-59999") == 2


async def test_ignores_a_200_that_would_send_the_whole_file() -> None:
    def whole_file(req: httpx.Request) -> httpx.Response:
        if req.headers.get("range") == "bytes=0-0":
            return httpx.Response(
                206, content=AUDIO[:1], headers={"content-range": f"bytes 0-0/{len(AUDIO)}"}
            )
        return httpx.Response(200, content=AUDIO)

    relay = StreamRelay(OneSource(), httpx.AsyncClient(transport=httpx.MockTransport(whole_file)))
    assert await collect(relay, "bytes=100-199") == b""
