# Contributing

Thanks for helping! Bug reports, fixes, docs and new languages for the voice model are all welcome.

## Development setup

You need [uv](https://docs.astral.sh/uv/) and, to run against real YouTube, [Deno](https://deno.com).

```bash
git clone https://github.com/denzilrdz/echo-tunes && cd echo-tunes
uv sync                       # creates .venv with the app and dev tools from uv.lock
uv run pytest                 # tests run offline, with fakes for YouTube and Amazon
```

Before opening a pull request:

```bash
uv sync --locked                # the same versions CI uses
uv run ruff format src tests scripts
uv run ruff check src tests scripts
uv run zizmor --persona=auditor .github/ && uv run actionlint   # if you changed a workflow
uv run mypy
uv run pytest
scripts/check-private-info.sh   # no IP addresses, tailnet names or real IDs (+ .private-ids)
```

`check-private-info.sh` also reads an optional `.private-ids` file in the repository root:
your own values that must never be committed (the ends of your Echos' device IDs, your
tailnet or domain name), one per line, `#` for comments. It's in `.gitignore`, so it stays
on your machine; the script fails if any tracked file contains one of them (case-insensitive).

Fuzzing (Linux only, Atheris): `uv sync --group fuzz && uv run python fuzz/fuzz_tokens.py
-max_total_time=60`. CI fuzzes weekly; see `fuzz/README.md`.

Run it locally (needs a public HTTPS address for Alexa to reach it, see docs/PUBLIC_HTTPS.md,
and [Deno](https://deno.com) on your `PATH` for yt-dlp). Data goes to `./data` unless you set
`ECHO_TUNES_DATA_DIR`; the dashboard is on <http://localhost:8081>:

```bash
cp .env.example .env && $EDITOR .env
uv run echo-tunes doctor
uv run echo-tunes serve
```

Or build the image: `docker build -t echo-tunes:dev .`

## How changes land

`main` is protected: changes arrive through a pull request (squash-merged), CI (`quality` and
`docker`) must pass, CodeQL must report no high-severity findings, review threads must be
resolved, and commits must be signed
([how to sign commits](https://docs.github.com/authentication/managing-commit-signature-verification)).
Workflows from first-time contributors run after a maintainer approves them.

## Guidelines

- **Dependencies** are managed with uv: `uv add <package>` (or `uv add --dev`), and commit
  `pyproject.toml` with `uv.lock`.
- **Memory must stay flat.** Anything that keeps data between requests must have a size limit
  (use `BoundedTTLCache`). `tests/test_memory.py` checks this; don't loosen it to make a test pass.
- **Keep it small.** echo-tunes aims to be the simple option. Big features are better discussed
  in an issue first.
- **Voice model changes**: edit `scripts/build_voice_model.py`, then run
  `uv run python scripts/build_voice_model.py` (a test fails if the generated files are stale).
  New languages are welcome.
- **Commits** follow [Conventional Commits](https://www.conventionalcommits.org):
  `feat: …`, `fix: …`, `docs: …`, `chore(deps): …`.
- Add a line to `CHANGELOG.md` under `[Unreleased]` for user-visible changes.

## Releasing (maintainers)

1. Move `[Unreleased]` in `CHANGELOG.md` to the new version and update `version` in `pyproject.toml`.
2. Commit, then tag: `git tag -s v0.2.0 -m v0.2.0 && git push origin main v0.2.0`.
3. The release workflow publishes `ghcr.io/denzilrdz/echo-tunes:<version>` for amd64 and arm64.
