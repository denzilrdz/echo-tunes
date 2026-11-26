---
name: security-checklist
description: Security rules for echo-tunes. Use before merging anything that touches request handling, the dashboard or its API, tokens, settings, logging, workflows or the Docker image, and when answering a security report.
---

# Security checklist

## Public port (8080)

- [ ] `/alexa` verifies every request (`alexa/verify.py`): cert URL rules (ASCII, full match),
      chain to a trusted root with name `echo-api.amazon.com`, RSA-SHA256 signature over the
      exact body, timestamp within 150 s, skill ID. Each rejection carries a fixed `reason`.
- [ ] Bodies are capped while reading (chunked requests have no Content-Length).
- [ ] Stream links are HMAC-signed (128-bit) and expire; characters are checked before decoding.
- [ ] No new public routes. `/healthz` reveals no version.
- [ ] Nothing a client sends can hold resources without a total bound (slots, timeouts).

## Private port (8081)

- [ ] Host allowlist (`host_allowed`): IPs, localhost, the public URL's name and
      `DASHBOARD_HOSTS` only (blocks DNS rebinding). Cross-site `Sec-Fetch-Site` is refused.
- [ ] Strict CSP, no inline script/style; the page only ever inserts text (`textContent`).
- [ ] **State-changing endpoints** (play, queue, clear history): POST only, password required
      (refuse when none is set), same-origin check (`Origin`/`Sec-Fetch-Site`), bounded inputs.
- [ ] `/metrics` and the API sit behind the same password when one is set.
- [ ] Browsers sign in on `/login` (session cookie: `<expiry>.<HMAC keyed by the password>`,
      HttpOnly, SameSite=Lax, Secure behind HTTPS; `DASHBOARD_SESSION_DAYS`, 0 = no expiry and
      renewed on each visit). Scripts use Basic auth. Only `/login`, `/api/login`, `/static/*`,
      the manifest and `/sw.js` are public; no `WWW-Authenticate` for browser requests (no
      pop-up). Every wrong password (sign-in or Basic) waits 1 s behind one shared lock: no
      per-address lockout (behind a proxy everyone shares one address).

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
- [ ] No caches in `release.yml`; the release checks tag == version and runs tests first.
- [ ] zizmor (auditor) and actionlint clean.
- [ ] Image: non-root uid 10001, read-only root filesystem works, all capabilities dropped.

Report path for others: SECURITY.md (private vulnerability reporting on GitHub).
