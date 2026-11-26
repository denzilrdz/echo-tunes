# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org).

## [Unreleased]

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
