# CLAUDE.md

echo-tunes: a self-hosted Alexa **custom skill** that plays YouTube Music on an Echo. One
Python 3.13+ process (FastAPI + uvicorn) in one Docker image, with two ports:

- **public 8080**: `POST /alexa` (Amazon-signed requests), `GET /stream/<token>.m4a` (audio
  relay), `/healthz`, `/`. Something else (Caddy, Cloudflare Tunnel, Tailscale Funnel, any
  proxy) puts HTTPS in front of it. Nothing in the code may assume a particular host or tunnel.
- **private 8081**: the dashboard and web player (React app in `web/`, built into
  `src/echo_tunes/web/dist/`; an installable PWA),
  its JSON API and `/metrics`. Never published to the internet.

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
(cd web && npm ci && npm run build)          # web app -> src/echo_tunes/web/dist (commit it)
(cd web && npm run dev)                       # Vite dev server; proxies /api to :18081
(cd web && npm run lint && npm run typecheck && npm test && npm run size)
(cd web && npm run e2e)                       # Playwright, real CSP; needs site/ (next line)
uv run python scripts/build_demo.py site      # GitHub Pages: landing page + web player demo
uv run --with pillow python scripts/screenshots.py [--icons]   # docs/img, social, PWA shots
uv run python scripts/build_voice_model.py    # skill-package voice models, all locales
```

## Layout

```
src/echo_tunes/
  app.py            public app + build_services() (the composition root)
  dashboard.py      private app: API, player routes, PWA manifest + /sw.js, CSP, Host
                    allowlist, sign-in/Basic/Bearer auth, 256 KB body cap; actions = POST
                    JSON, same-origin, password set
  sessions.py       dashboard sign-in sessions (session.key + sessions.json, bounded)
  alexa/            verify.py (request signatures), skill.py (intents + AudioPlayer events),
                    responses.py (directive builders)
  music/            catalog.py (ytmusicapi), browse.py (validated items for the player),
                    resolver.py (yt-dlp in worker processes),
                    extract.py (runs inside a worker), account.py (Google sign-in)
  player/           state.py (queue, tokens, shuffle), store.py (SQLite, per Echo)
  stream.py         audio relay: ranges, warm-up 403s, slots, write timeout
  history.py        play history (SQLite, retention), stats
  metrics.py        Prometheus registry (fixed label values only)
  checks.py         setup checks shared by `doctor` and the dashboard
  web/dist/         the built web app (generated from web/, committed, never edited)
tests/              pytest; fakes in conftest.py; property, state-machine and memory tests
fuzz/               Atheris fuzzers (Linux), weekly in CI
web/                the web app: React + TypeScript + Vite + Tailwind 4 + Base UI (skill web-ui)
demo/ scripts/      landing page, social image, screenshots, voice model
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
- **Dashboard pages follow a strict CSP** (`script-src 'self'; style-src 'self'`): no inline
  scripts, `<style>` elements or `style=""` attributes; React's `style` prop is fine (CSSOM).
  Base UI runs inside `<CSPProvider disableStyleElements>`; avoid libraries that inject
  `<style>` (skill `web-ui`). `npm run e2e` fails on any CSP violation.
- **The committed build must match `web/`**: change the app, then `npm run build` and commit
  `src/echo_tunes/web/dist` (CI diffs it). `dashboard.page_html()` fills the app name and
  accent into the placeholders in `web/index.html`; keep them.
- **The Pages demo is the real build** plus `<meta name="echo-tunes-demo">`, which makes the app
  load `web/src/demo/demo-api.ts` (fake API). It must answer every API call the app makes.
- **The player can't control an Echo directly**: picks are applied in the reply to the Echo's
  next event (`PlayerState.pending`, `Skill._pending_jump`), and `PlayerState.enqueued` tracks
  the song the Echo has already lined up. See skill `alexa-playback`.
- **Never block the event loop on I/O in `/alexa`**: `AlexaVerifier.verify_async` checks a
  cached certificate inline (CPU only) and sends every download to its bounded pool.
- **`scripts/check-private-info.sh` reads `.private-ids`** (untracked): put your own device-ID
  tails and host names there.
- **PWAs install only over HTTPS** (or localhost); the service worker is served from `/sw.js`
  so its scope is the whole dashboard, and never caches `/api`.
- **Amazon's certificate file names vary**: only the `/echo.api/` folder rule is Amazon's.
  0.2.1-0.2.2 refused every real request with a stricter pattern; test changes to
  `alexa/verify.py` in the developer console's simulator before releasing (skill `release`).
- **`uv lock --exclude-newer` saves the cutoff in `uv.lock`**, and `uv sync --locked` then
  fails; `yt-dlp.yml` runs a plain `uv lock` after it to drop it. That workflow opens its
  PR with `github.token`, which needs the repo setting "Allow GitHub Actions to create and
  approve pull requests".
- **Screenshots force the theme with `?theme=light|dark`** (and `?shots` for made-up songs);
  `boot.js` moves the page's `?query` out of the address bar before the hash router starts.

## Skills (.claude/skills/)

`alexa-playback`, `streaming`, `testing`, `security-checklist`, `web-ui`, `release`.
