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
uv run ruff format src tests
uv run ruff check src tests
uv run mypy
uv run pytest
scripts/check-private-info.sh   # no IP addresses, tailnet names or real IDs
```

Run it locally (needs a public HTTPS address for Alexa to reach it, see docs/PUBLIC_HTTPS.md):

```bash
cp .env.example .env && $EDITOR .env
uv run echo-tunes doctor
uv run echo-tunes serve
```

Or build the image: `docker build -t echo-tunes:dev .`

## Guidelines

- **Dependencies** are managed with uv: `uv add <package>` (or `uv add --dev`), and commit
  `pyproject.toml` with `uv.lock`.
- **Memory must stay flat.** Anything that keeps data between requests must have a size limit
  (use `BoundedTTLCache`). `tests/test_memory.py` checks this; don't loosen it to make a test pass.
- **Keep it small.** echo-tunes aims to be the simple option. Big features are better discussed
  in an issue first.
- **Voice model changes**: edit `skill-package/interactionModels/custom/en-US.json` and copy it
  to the other English locales (a test checks they match). New languages are welcome as new files.
- **Commits** follow [Conventional Commits](https://www.conventionalcommits.org):
  `feat: …`, `fix: …`, `docs: …`, `chore(deps): …`.
- Add a line to `CHANGELOG.md` under `[Unreleased]` for user-visible changes.

## Releasing (maintainers)

1. Move `[Unreleased]` in `CHANGELOG.md` to the new version and update `version` in `pyproject.toml`.
2. Commit, then tag: `git tag -s v0.2.0 -m v0.2.0 && git push origin main v0.2.0`.
3. The release workflow publishes `ghcr.io/denzilrdz/echo-tunes:<version>` for amd64 and arm64.
