# CLAUDE.md

echo-tunes: a self-hosted Alexa **custom skill** that plays YouTube Music on an Echo. One
Python 3.13+ process (FastAPI + uvicorn) in one Docker image, with two ports:

- **public 8080**: `POST /alexa` (Amazon-signed requests), `GET /stream/<token>.m4a` (audio
  relay), `/healthz`, `/`. Something else (Caddy, Cloudflare Tunnel, Tailscale Funnel, any
  proxy) puts HTTPS in front of it. Nothing in the code may assume a particular host or tunnel.
- **private 8081**: the dashboard (`src/echo_tunes/web/`), its JSON API and `/metrics`. Never
  published to the internet.

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before changing playback, streaming or
memory handling. User docs: README.md and docs/.

## Commands

```bash
uv sync --locked                              # .venv from uv.lock (app + dev tools)
uv run pytest -q                              # offline: fakes for YouTube and Amazon
uv run ruff format src tests scripts && uv run ruff check src tests scripts
uv run mypy                                   # strict
uv run zizmor --persona=auditor .github/ && uv run actionlint   # after touching workflows
scripts/check-private-info.sh                 # no real IPs, tailnet names or IDs (CI runs it)
uv run echo-tunes doctor | serve | login | logout   # needs .env (see .env.example) and Deno
docker build -t echo-tunes:dev .
uv run python scripts/build_demo.py site      # GitHub Pages: landing page + dashboard demo
uv run --with pillow python scripts/screenshots.py   # docs/img/*.png + social preview
uv run python scripts/build_voice_model.py    # skill-package voice models, all locales
```

## Layout

```
src/echo_tunes/
  app.py            public app + build_services() (the composition root)
  dashboard.py      private app: API, CSP, Host allowlist, optional Basic auth
  alexa/            verify.py (request signatures), skill.py (intents + AudioPlayer events),
                    responses.py (directive builders)
  music/            catalog.py (ytmusicapi), resolver.py (yt-dlp in worker processes),
                    extract.py (runs inside a worker), account.py (Google sign-in)
  player/           state.py (queue, tokens, shuffle), store.py (SQLite, per Echo)
  stream.py         audio relay: ranges, warm-up 403s, slots, write timeout
  history.py        play history (SQLite, retention), stats
  metrics.py        Prometheus registry (fixed label values only)
  checks.py         setup checks shared by `doctor` and the dashboard
  web/              dashboard HTML/CSS/JS (no build step, no inline script)
tests/              pytest; fakes in conftest.py; property, state-machine and memory tests
fuzz/               Atheris fuzzers (Linux), weekly in CI
demo/ scripts/      Pages site, screenshots, voice model
skill-package/      Alexa skill manifest + voice models (generated)
examples/           compose setups: caddy, cloudflare-tunnel, tailscale-funnel
```

## Rules

- **Memory stays flat.** Every cache is a `BoundedTTLCache` or capped; every per-device or
  per-link structure has a limit; yt-dlp runs in recycled worker processes. A feature that
  keeps anything per request needs a bound and a line in `tests/test_memory.py`'s scope.
- **Anything a client can drive needs a total bound**, not just a per-call timeout: body
  sizes, streams per link and in total (`StreamSlots`), write timeouts (`AudioResponse`).
- **Alexa's rules** (skill `alexa-playback`): ~8 s to answer, no speech in AudioPlayer or
  PlaybackController responses, `PlaybackNearlyFinished` arrives once per song.
- **Metrics labels** are fixed sets; never put titles, IDs or error text in a label.
- **Logs never contain** stream tokens, YouTube URLs (they carry the server's IP) or tokens.
  The public port has no access log for that reason.
- **Private dashboard:** read-only endpoints may be open on a private network; anything that
  changes state needs the dashboard password and a same-origin check (skill
  `security-checklist`).
- **Public repo:** no private addresses, tailnet names, device or skill IDs anywhere
  (`scripts/check-private-info.sh`). Examples use `music.example.com` and `203.0.113.x`.
- Settings are `ECHO_TUNES_*` env vars in `config.py`; validate them there (friendly errors
  come from `cli._settings()`), and document every new one in README's table and
  `.env.example`.
- Type hints everywhere (mypy strict), `ruff` at 100 columns, plain English in docs and
  user-facing strings.

## Testing rule

Every fix comes with a test that fails without it, written in the order the Echo really sends
events (skill `testing`). `uv run pytest` must pass before every commit; CI also runs Python
3.15 and the lowest allowed dependency versions.

## Git rules

- Branch + pull request into `main` (protected: CI must pass, signed commits, linear history).
  Squash-merge. Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `test:`).
- GPG-signed commits and tags. Never change global git config. Ask before pushing.
- `gh` may be logged in to a work account: use
  `GH_TOKEN=$(gh auth token --user denzilrdz) gh ...` for this repo.
- User-visible changes go in `CHANGELOG.md` under `[Unreleased]`.
- Releases: skill `release`.
- When you learn a new command, gotcha or convention, update this file or the relevant skill
  in the same pull request.

## Gotchas

- **YouTube links 403 for ~2 s after they're issued**; `StreamRelay` waits it out
  (`WARMUP_SECONDS`). Links are tied to the server's IP, so the Echo can't fetch YouTube
  directly: audio is always relayed.
- **yt-dlp needs Deno** (JavaScript challenges). The image ships it; `doctor` checks it.
- **Python 3.15 in the image, 3.13 minimum.** CI tests both.
- **pydantic-settings parses list env vars as JSON** unless the field is `NoDecode`
  (needs pydantic-settings >= 2.7).
- **ProcessPoolExecutor uses spawn**: worker code must be importable without side effects
  (`if __name__` guards in scripts).
- **uvicorn's signal handler re-raises** after shutdown; `cli.serve()` installs its own.
- **The invocation name is "my tunes"**: Amazon rejects names containing a wake word ("echo").
- **Dashboard pages follow a strict CSP** (no inline scripts or styles); the demo injects data
  through `window.ECHO_TUNES_DEMO`.
- **Headless Chrome ignores `prefers-color-scheme`** for screenshots: `scripts/screenshots.py`
  makes themed CSS copies.

## Skills (.claude/skills/)

`alexa-playback`, `streaming`, `testing`, `security-checklist`, `web-ui`, `release`.
