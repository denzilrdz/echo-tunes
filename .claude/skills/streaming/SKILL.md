---
name: streaming
description: The audio relay and the yt-dlp resolver. Use when changing src/echo_tunes/stream.py, music/resolver.py or music/extract.py, the /stream route, or when songs fail to start, stop part-way, 502, or memory/connections grow under streaming.
---

# Streaming and resolving

## Resolver (`music/resolver.py`)

- yt-dlp runs in a `ProcessPoolExecutor` (spawn, `max_tasks_per_child`): memory is returned
  when a worker is recycled.
- One lookup per song at a time: `_inflight` holds an **asyncio Task**; callers `shield()` it,
  so a caller that gives up doesn't cancel it for others.
- A lookup over `RESOLVE_TIMEOUT` restarts the pool (terminating the stuck worker). Lookups
  that were sharing the old pool see `BrokenProcessPool`/a cancelled future and **retry once**
  on the new pool.
- Results are cached until shortly before YouTube's expiry (`EXPIRY_MARGIN`).
- Tests: `tests/test_resolver.py` swaps the pool for threads and `extract.resolve` for a fake.

## Relay (`stream.py`)

- New YouTube links answer **403 for ~2 s**: `_wait_until_ready` probes `bytes=0-0` until 206
  (up to `WARMUP_SECONDS`). Probes use their own small httpx pool.
- Bodies are fetched in `UPSTREAM_SPAN` ranges (YouTube throttles huge ones) and passed on in
  `CHUNK`s; a song is never held in memory.
- Transport errors resume from the same byte (`MAX_RETRIES` in a row). A 403/410 mid-song
  refreshes the link once (invalidate, resolve, wait ready) and continues.
- `StreamSlots`: at most `MAX_STREAMS` in total and `MAX_STREAMS_PER_LINK` per token
  (429/503 beyond). `AudioResponse` drops a client that reads nothing for `SEND_TIMEOUT` and
  never completes a body shorter than its Content-Length (the server closes the connection,
  the Echo retries with a Range).
- Ranges follow RFC 9110: anything not understood is ignored (200 with the whole file); only a
  well-formed range past the end is 416.
- `echo_tunes_streams_total{outcome}`: ok, cut_short, client_gone, client_stalled, too_many,
  bad_link, youtube_error, range_error, error. Keep docs/MONITORING.md in sync.

## Don'ts

- Don't log stream tokens or YouTube URLs (the public port has no access log for this reason).
- Don't share the body client with anything else; don't add an unbounded per-stream structure.
