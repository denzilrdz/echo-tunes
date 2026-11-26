---
name: release
description: Cut an echo-tunes release (version bump, changelog, signed tag, GitHub release, image) and roll it out. Use when asked to release, tag, publish a version, or update a deployment to a new version.
---

# Release

1. **Prepare** on a branch `chore/release-X.Y.Z`:
   - `version` in `pyproject.toml`, then `uv lock` (the lock records it).
   - `CHANGELOG.md`: rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, add an empty
     `[Unreleased]`, update the compare links at the bottom.
   - Image tag in `compose.yaml` and `examples/*/compose.yaml` (the `image:` line and the
     digest-pinning comment above it).
   - Open a PR, wait for CI, squash-merge.
2. **Tag** on the updated `main`: `git tag -s vX.Y.Z -m "echo-tunes X.Y.Z"`, check with
   `git verify-tag`, then `git push origin vX.Y.Z` (ask first). To try a release on a real
   Echo first, tag `vX.Y.Z-rc.N` (same pyproject version): it publishes image `X.Y.Z-rc.N` as a
   GitHub pre-release and leaves `latest` alone. Test in the Alexa developer console's
   simulator (Test tab) and on the Echo, then tag `vX.Y.Z`.
3. **Watch** `release.yml`: `check` (tag == version, tests) → `image` (multi-arch to ghcr.io
   with provenance, `latest` only for non-pre-releases) → wheel + sdist + `SHA256SUMS` +
   `echo-tunes-vX.Y.Z.intoto.jsonl` on a GitHub release (immutable once published).
   `gh release view vX.Y.Z --json assets -q '.assets[].name'` must list all four.
4. **Check** Scorecard after a few minutes (`api.securityscorecards.dev`); Signed-Releases
   needs the `.intoto.jsonl` file.
5. **Roll out**: on a self-hosted install, bump the image tag in its compose file and
   `docker compose pull && docker compose up -d`, then `echo-tunes doctor`.

Never move or delete a published tag: releases are immutable. Fix forward with a new version.
