# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org).

## [Unreleased]

### Fixed

- **Shuffle no longer stops the music** after the current song. Reordering or trimming the
  queue kept a stale token for the playing song, so nothing was queued next, its history row
  stayed open and resume ignored the position. Tokens are now matched by song within the queue.
- Play requests answer Alexa after the search only; the radio is fetched afterwards. YouTube
  Music calls time out after 5 s and no longer wait behind one another, so a slow YouTube can't
  make Alexa give up (~8 s).
- Fake `/alexa` requests can no longer tie up shared threads: only Amazon's certificate file
  names are fetched, failures are remembered for 10 minutes, and verification has its own
  thread pool.
- A pause and resume counts as one play (history and YouTube history).
- A YouTube lookup that times out restarts the worker processes instead of blocking them.
- The Setup page no longer loads yt-dlp into the server, and runs `deno --version` with a timeout.
- `docker stop` shuts down cleanly (exit 0) instead of being killed before cleanup.
- The stream-link key is written atomically; a damaged key stops start-up with a clear message.
- An unknown mix name says it wasn't found instead of playing another mix.

### Changed

- `echo-tunes logout` keeps the saved Google OAuth client (`--forget-client` removes it too).
- The daily yt-dlp update tests new versions without write access and only takes versions that
  are at least a day old.
- Example compose files pin third-party images by digest (kept current by Dependabot); CI also
  formats and lints `scripts/`.

## [0.2.0] - 2026-11-26

### Added

- **Private dashboard** on a second port (`ECHO_TUNES_DASHBOARD_PORT`, default 8081): now playing
  and up next per Echo with live progress, play history with search and filters, stats (plays,
  listening time, top songs and artists, plays per day), a monitoring page with copy-ready
  settings, and a **setup checklist with a Test play button**. Read-only, strict security
  headers, optional password. See docs/DASHBOARD.md.
- **Play history** in SQLite, kept for `ECHO_TUNES_HISTORY_DAYS` (default 15) and pruned
  automatically; records why each song played and whether it finished, was skipped, paused or
  failed.
- **Prometheus metrics** at `/metrics` and a JSON **health check** at `/api/health` for Uptime
  Kuma and similar tools. See docs/MONITORING.md.
- `ECHO_TUNES_DEVICE_NAMES` for friendly Echo names.
- `echo-tunes doctor` and the dashboard share one set of checks, now including "has Alexa
  reached this server?" and the age of yt-dlp.

### Fixed

- The spoken name is now **"my tunes"** ("Alexa, ask my tunes to play …"). Amazon refuses to
  build a skill whose invocation name contains a wake word, and "echo" is one.
- YouTube's signed audio links (which include the server's IP address) are no longer written
  to the log at the default log level.

## [0.1.0] - 2026-11-26

First release.

### Added

- Optional YouTube Music sign-in with `echo-tunes login` (Google device sign-in with your own
  OAuth client, or `--browser` with pasted headers) and `echo-tunes logout`. Tokens are stored
  in the data folder with owner-only permissions; audio is still fetched without the account.
- Voice commands for your library: play my liked songs, play my playlist …, play my supermix /
  discover mix / replay mix, and like this song. Playlist names are matched loosely.
- Optional `ECHO_TUNES_SEND_HISTORY` adds played songs to your YouTube history.
- `doctor` reports the sign-in status and checks the library can be read.
- `scripts/build_voice_model.py` generates every locale's voice model from one definition.

### Fixed

- `/alexa` now caps the body size while reading it, so a chunked request without
  `Content-Length` can't be read without limit.
- CI's secret scan works on pull requests from Dependabot.

- Alexa skill endpoint (`POST /alexa`) with Amazon request verification: certificate URL rules,
  certificate chain and name, RSA-SHA256 body signature, 150-second timestamp window and skill
  ID check, with a bounded certificate cache and download timeout.
- Voice commands: play a song or artist, play radio for a song, what's playing, and all
  AudioPlayer controls (pause, resume, next, previous, start over, repeat, shuffle, loop).
- Endless radio: each song starts a YouTube Music radio and the queue tops itself up.
- Audio relay (`GET /stream/<token>.m4a`) with signed, expiring links, `Range` support,
  YouTube warm-up handling, bounded upstream requests and resume after network errors.
- yt-dlp runs in recycled worker processes; the next song is prepared in the background.
- Per-Echo player state in SQLite, capped at 200 songs per Echo and 50 Echos.
- `echo-tunes doctor` self-check; `/healthz` with memory use.
- Docker image (Python 3.13, Deno, non-root, read-only friendly) and compose examples for
  Tailscale Funnel, Cloudflare Tunnel, Caddy and a plain setup.
- Voice model for en-US, en-GB, en-IN, en-CA and en-AU.
- Documentation: setup guide, public HTTPS options, voice commands, architecture, troubleshooting.
- CI: lint, type check, tests including a memory soak test, privacy check, secret scan,
  workflow audit, Docker smoke test; multi-arch release workflow; daily yt-dlp update PRs.

[Unreleased]: https://github.com/denzilrdz/echo-tunes/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/denzilrdz/echo-tunes/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/denzilrdz/echo-tunes/releases/tag/v0.1.0
