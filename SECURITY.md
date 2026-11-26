# Security policy

echo-tunes is reachable from the internet (Amazon's servers and your Echo must reach it), so
security reports are very welcome.

## Supported versions

Only the latest release (and `main`) receives security fixes.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

- Use GitHub's private reporting: _Security → Report a vulnerability_ on this repository, or
- email **denzil.rdz@gmail.com** with the subject `echo-tunes security`.

Include the affected version or commit, how you host it, steps to reproduce and the impact you
expect. You'll get an acknowledgement within 7 days; a fix or a plan should follow within 30
days for confirmed issues. Credit is given in the release notes unless you prefer otherwise.

## Scope

In scope: Alexa request verification (`src/echo_tunes/alexa/verify.py`), stream link signing
(`src/echo_tunes/tokens.py`), the stream relay, the Docker image and the CI/release workflows.

Out of scope: vulnerabilities in yt-dlp, ytmusicapi, Deno or your HTTPS front end (report those
upstream), and YouTube refusing to serve audio.

## Design notes

How requests are verified, how stream links are signed and how the container is hardened is
described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#security).
