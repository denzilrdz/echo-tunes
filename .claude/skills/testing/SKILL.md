---
name: testing
description: How echo-tunes is tested. Use when writing or fixing tests, adding fakes, when CI's quality job fails (Python 3.15, lowest versions, memory soak), or when adding fuzzers or property tests.
---

# Testing

All tests are offline: no YouTube, no Amazon.

| File                                 | Covers                                                                                                                                                                    |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `conftest.py`                        | `FakeCatalog` (set `catalog.failing = {"radio", ...}` to make methods raise), `FakeResolver`, `FakeAmazon` (a test CA that signs requests), `intent()`/`event()` builders |
| `test_skill.py`, `test_failures.py`  | intents, AudioPlayer events, buttons, failures                                                                                                                            |
| `test_queue_machine.py`              | Hypothesis state machine over `PlayerState`                                                                                                                               |
| `test_properties.py`                 | tokens, ranges, cert URLs (Hypothesis)                                                                                                                                    |
| `test_stream.py`, `test_resolver.py` | relay with `httpx.MockTransport`; resolver with threads                                                                                                                   |
| `test_verify.py`                     | request signatures, every rejection reason                                                                                                                                |
| `test_dashboard.py`, `test_app.py`   | routes, CSP, Host allowlist, auth                                                                                                                                         |
| `test_cli.py`, `test_config.py`      | commands, settings validation                                                                                                                                             |
| `test_memory.py`                     | soak test: thousands of requests, tracemalloc growth < 512 KB                                                                                                             |

## Rules

- A bug fix's test must fail without the fix. For playback, send events in the Echo's real
  order: the review that found the shuffle bug showed a test can pass with an impossible order.
- Close what you open: unclosed SQLite connections or files fail the run (`filterwarnings`
  turns ResourceWarning into an error). The `skill` fixture closes its store and any
  `skill.history` a test sets; elsewhere call `.close()`. Find a leak's origin with
  `PYTHONTRACEMALLOC=15 uv run pytest -q`.
- The sdist must pass its own tests: `only-include` in pyproject.toml lists what they need.
- `await skill.wait_background()` after a play intent: the radio is fetched after answering.
- Don't leave global state changed (root logger level, env vars): the memory soak test runs in
  the same process and counts every captured log record.
- Fuzzers live in `fuzz/` (Atheris, Linux only): `uv sync --group fuzz && uv run python
fuzz/fuzz_tokens.py -max_total_time=60`.

## CI's matrix (`.github/workflows/ci.yml`, job `quality`)

`uv sync --locked`, ruff, mypy, pytest on 3.13, pytest on 3.15 (`UV_PROJECT_ENVIRONMENT=.venv-315`),
and pytest at the **lowest allowed versions** (`uv pip compile --resolution lowest-direct`).
If the last one fails, raise the floor in `pyproject.toml`, don't pin.
