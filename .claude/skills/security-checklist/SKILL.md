---
name: security-checklist
description: Security rules for echo-tunes. Use before merging anything that touches request handling, the dashboard or its API, tokens, settings, logging, workflows or the Docker image, and when answering a security report.
---

# Security checklist

## Public port (8080)

- [ ] `/alexa` verifies every request (`alexa/verify.py`): cert URL rules (ASCII, full match),
      chain to a trusted root with name `echo-api.amazon.com`, RSA-SHA256 signature over the
      exact body, timestamp within 150 s, skill ID. Each rejection carries a fixed `reason`.
- [ ] Bodies are capped while reading (chunked requests have no Content-Length) and must
      arrive within `BODY_READ_TIMEOUT` (10 s, reason `slow_body`).
- [ ] JSON, timestamp and skill ID are checked *before* any certificate download (and again
      after the signature); at most `MAX_PENDING_DOWNLOADS` downloads wait or run; a cached
      certificate is verified inline, never behind the download pool.
- [ ] The public server caps connections (`limit_concurrency`, 64); rejections are logged at
      most once per reason every 10 s (`RateLimitedLog`), counted in metrics every time.
- [ ] Stream links are HMAC-signed (128-bit) and expire; characters are checked before decoding,
      and only the canonical base64 spelling of the signature is accepted.
- [ ] No new public routes. `/healthz` reveals no version.
- [ ] Nothing a client sends can hold resources without a total bound (slots, timeouts).

## Private port (8081)

- [ ] Host allowlist (`host_allowed`): IPs, localhost, the public URL's name and
      `DASHBOARD_HOSTS` only (blocks DNS rebinding). Cross-site `Sec-Fetch-Site` is refused.
- [ ] Strict CSP, no inline script/style (web app: no `dangerouslySetInnerHTML`, no `<style>`
      injection; `npm run e2e` checks); the page only ever inserts text.
- [ ] Request bodies capped at 256 KB (`BodyLimit`: Content-Length and while reading);
      validation errors never echo the input.
- [ ] **State-changing endpoints** (play, queue, test play, clear history): POST only, password required
      (refuse when none is set), same-origin check (`Origin`/`Sec-Fetch-Site`), bounded inputs.
- [ ] `/metrics` and the API sit behind the same password when one is set.
- [ ] Browsers sign in on `/login` (`sessions.py`: cookie `<random id>.<issued>.<HMAC>`, keyed
      by `session.key` in the data folder mixed with a hash of the password, so a stolen
      cookie can't be brute-forced and a new password signs everyone out; the id must be in
      the server's list (max 100), so sign-out and *sign out everywhere*
      (`POST /api/logout/all`) really end sessions; the issue time is checked against the
      current `DASHBOARD_SESSION_DAYS`; HttpOnly, SameSite=Lax, Secure behind HTTPS).
      Google sign-in (`google_login.py`, only with a password set): device flow, scope
      `openid email`, ID token from the token endpoint checked for issuer, audience, expiry,
      `email_verified` and the `DASHBOARD_GOOGLE_EMAILS` allowlist; then the same session as
      the password. Pending flows capped (`MAX_PENDING`) and expiring; the browser polls with
      a 256-bit flow secret; starts are rate-limited (`MAX_STARTS`/min) and the cap is checked before calling Google; an in-use flow is never evicted; no Google token is kept or revoked (revoking would end the YouTube
      Music grant on the same client). `/api/login/options`, `/api/login/google[/poll]` are public.
      Monitors use `DASHBOARD_API_TOKEN` (Bearer, >= 32 chars, no gate); scripts may use Basic
      auth. Only `/login`, `/api/login*`, `/static/*`, `/assets/*` (the built app, no data),
      the manifest and `/sw.js` are public; no `WWW-Authenticate` for browser requests (no pop-up). Every password check (sign-in or
      Basic) waits for one shared gate *before* comparing SHA-256 digests (constant time
      whatever the length); a wrong one holds it 1 s; over 20 queued get 429. No per-address
      lockout (behind a proxy everyone shares one address).

## Data and logs

- [ ] Files in the data folder are owner-only (`os.umask(0o077)` in `serve`; key written
      atomically with 0600).
- [ ] Logs carry no stream tokens, YouTube URLs, OAuth tokens or cookies; httpx/httpcore stay
      at WARNING unless `debug`.
- [ ] Never commit `.env`, tokens, cookies or real IDs; `scripts/check-private-info.sh` and
      gitleaks run in CI.

## Workflows and image

- [ ] Actions pinned to full SHAs with a version comment; `persist-credentials: false`;
      per-job `permissions` with a comment per scope; no `${{ }}` inside `run:`.
- [ ] No caches in `release.yml` (setup-uv `enable-cache: false`, setup-qemu `cache-image:
      false` with the binfmt image pinned by digest, setup-buildx `cache-binary: false`,
      build-push `no-cache`); the release checks tag == version and runs tests first.
- [ ] `yt-dlp.yml`: artifacts that a privileged job uses are uploaded *before* untrusted code
      runs in the unprivileged job.
- [ ] zizmor (auditor) and actionlint clean.
- [ ] Image: non-root uid 10001, read-only root filesystem works, all capabilities dropped.

Report path for others: SECURITY.md (private vulnerability reporting on GitHub).
