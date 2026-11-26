# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org).

## [Unreleased]

## [0.3.0] - 2026-11-26

A web player, and the dashboard becomes an app you can install on your phone.

### Added

- **Web player** (new first tab): search songs, albums, artists and playlists; browse quick
  picks, your mixes and library (when signed in), trending charts, top artists, and moods &
  genres. Play in the browser with a queue, radio that keeps going, media keys and lock-screen
  controls, or pick an Echo under *Play on* to queue songs there (*Play*, *Next*, *Add to
  queue*, *Radio*). Songs picked for an Echo play after the current song: Alexa only lets a
  skill change playback when the Echo checks in.
- `ECHO_TUNES_EXPERIMENTAL_SKIP`: let the player try to skip the song playing on an Echo by
  cutting its audio stream (works only while the Echo is still downloading it; off by default).
- **Install as an app** (PWA): manifest, icons and a service worker, so the dashboard can be
  added to a phone's home screen when opened over HTTPS. `ECHO_TUNES_APP_NAME`,
  `ECHO_TUNES_APP_COLOR` and `ECHO_TUNES_APP_ICON` change its name, colour and icon.
- **Clear history** on the History tab.
- Player and browse endpoints in the JSON API (docs/DASHBOARD.md).

### Changed

- Actions on the dashboard (play, queue, skip, clear history) need
  `ECHO_TUNES_DASHBOARD_PASSWORD` to be set, and are only accepted as same-origin JSON requests.
  Browsing and the read-only pages work as before.
- The dashboard's content security policy allows artwork from Google's image servers
  (`*.googleusercontent.com`, `yt3.ggpht.com`) besides `i.ytimg.com`.
- README, landing page, screenshots and social preview lead with the player.
- Release candidates: a `vX.Y.Z-rc.N` tag publishes a pre-release image to try before `vX.Y.Z`.

### Fixed

- **Alexa requests were refused since 0.2.1** ("There was a problem with the requested skill's
  response"): the signing-certificate check only accepted one file-name pattern, and Amazon's
  real file names differ. Any plain `.pem` file in Amazon's `/echo.api/` folder is accepted
  again (the folder, host, HTTPS and certificate chain checks are unchanged), and refused URLs
  are logged.

## [0.2.2] - 2026-11-26

Fixes from a full review of 0.2.1.

### Fixed

- **"Shuffle", "loop on" or "loop off" part-way through a song no longer stops the music** when
  that song ends. The Echo asks for its next song only once, usually before you speak; the
  answer now swaps in the new next song (`REPLACE_ENQUEUED`) instead of only clearing it.
- One YouTube lookup timing out no longer makes every other lookup in progress fail: they
  retry once on the restarted workers. A cancelled request no longer fails others waiting on
  the same song, and the finished lookup is kept.
- **One stream link can no longer stop audio on every Echo.** Streams are capped per link (3)
  and in total (24), clients that stop reading are dropped after 30 s, start-up probes have
  their own connection pool, and the public port no longer writes stream links to its log.
- A YouTube link that expires part-way through a song is refreshed and the song continues.
- When the song queued *next* fails to load, the playing song is no longer cut off; when the
  last song fails, the radio is extended.
- "Play my second mix" (and other mix synonyms) play the right mix.
- "Resume" after a song ended plays the next song instead of the last second of the old one.
  Loop with a one-song queue works; shuffle off restores the original order; with shuffle on,
  a new playlist starts on a random song.
- Plays per day are counted in your browser's time zone, not the server's (UTC in Docker).
- Settings: `ECHO_TUNES_LOG_LEVEL` only accepts real levels (`warn`/`trace` crashed start-up),
  and a public URL with a path, a dashboard host with a port, a device name with a comma or a
  missing cookies file are refused with a clear message.
- `doctor` checks your YouTube Music library can be read, and stops Deno if it hangs.
- The rejected-request metric gets its reason from where the request was rejected (some were
  mislabelled). Songs cut short are counted as `cut_short`, not `ok`.
- The Docker health check follows `ECHO_TUNES_PORT`.
- Byte ranges follow RFC 9110 (unknown or invalid ranges get the whole file, not a 416).

### Changed

- Requires pydantic-settings 2.7 or later (it was already needed). CI also tests the lowest
  allowed versions.
- The data folder defaults to `./data` outside Docker (the image still uses `/data`), and its
  files are readable by the owner only. History and queue databases flush to disk less often
  (faster on SD cards; a power cut can lose the last few plays, never corrupt the file).
- The public `/healthz` no longer shows the version (the private `/api/health` does).
- Releases check the tag matches the package version and run the tests before publishing,
  build without shared caches, and don't move `latest` for pre-releases. The daily yt-dlp
  pull request now runs the CI checks.
- The source package only contains what's needed to build and test.
- The README quick start, setup guide and landing page no longer lead with Tailscale: they start
  from the plain `compose.yaml` and offer Caddy (cloud server), Cloudflare Tunnel, Tailscale
  Funnel or your own reverse proxy as equal choices. Example addresses use `music.example.com`.
- Documented every setting (`ECHO_TUNES_DATA_DIR`, `ECHO_TUNES_HOST`, ranges), how to run
  without Docker, and the current `doctor` output.
- `CLAUDE.md` and task playbooks in `.claude/skills/` for working on the code with Claude Code.

## [0.2.1] - 2026-11-26

### Added

- A landing page at https://denzilrdz.github.io/echo-tunes/ with search and link-preview
  metadata (description, Open Graph, structured data, sitemap), screenshots in the README and
  docs, and a social preview image. `scripts/screenshots.py` regenerates them from the demo
  with made-up songs and generated artwork (no real album art in the repo).
- Coverage-guided fuzzing (Atheris) of stream links, `Range` headers, Amazon certificate URLs
  and player state, weekly and on changes (`fuzz/`, `.github/workflows/fuzz.yml`).
- Releases carry the Python package (wheel and source), `SHA256SUMS` and signed SLSA build
  provenance (`echo-tunes-<tag>.intoto.jsonl`), like the container image.
- CI tests on Python 3.13 and on 3.15, the Docker image's version.
- A public [dashboard demo](https://denzilrdz.github.io/echo-tunes/) with sample data, built
  from the real dashboard files and published to GitHub Pages.

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

- The Docker image runs Python 3.15.
- Stream links must use exactly the characters they're made of (ASCII digits, URL-safe base64)
  before anything is decoded; Python 3.15 warns that lenient base64 decoding is going away.
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

[Unreleased]: https://github.com/denzilrdz/echo-tunes/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/denzilrdz/echo-tunes/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/denzilrdz/echo-tunes/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/denzilrdz/echo-tunes/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/denzilrdz/echo-tunes/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/denzilrdz/echo-tunes/releases/tag/v0.1.0
