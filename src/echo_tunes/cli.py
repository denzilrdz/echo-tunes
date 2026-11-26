"""Command line: ``echo-tunes serve`` runs the server, ``echo-tunes doctor`` checks the setup."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import subprocess
import sys
import time

import httpx
from pydantic import ValidationError

from echo_tunes import __version__
from echo_tunes.config import Settings

CLOUD_HINT = " (on a cloud server YouTube may block the IP: see docs/TROUBLESHOOTING.md)"
TEST_SONG = "dQw4w9WgXcQ"  # a long-lived, globally available video used only for the self-test


def _settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        print("Configuration problem (check your environment variables or .env file):\n")
        for err in exc.errors():
            field = "ECHO_TUNES_" + "_".join(str(p) for p in err["loc"]).upper()
            print(f"  {field}: {err['msg']}")
        sys.exit(2)


def serve() -> None:
    import uvicorn

    from echo_tunes.app import create_app

    settings = _settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        proxy_headers=True,
        timeout_graceful_shutdown=5,
        server_header=False,
    )


def doctor() -> None:
    """Run every check and print a ✓/✗ list; exit 1 if anything failed."""
    failures = 0

    def report(ok: bool, label: str, detail: str = "") -> None:
        nonlocal failures
        failures += not ok
        print(f"  {'✓' if ok else '✗'} {label}" + (f": {detail}" if detail else ""))

    print(f"echo-tunes {__version__} doctor\n")
    settings = _settings()
    report(
        True,
        "Configuration",
        f"public URL {settings.base_url}, {len(settings.skill_ids)} skill ID(s)",
    )

    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.data_dir / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        report(True, "Data folder is writable", str(settings.data_dir))
    except OSError as exc:
        report(False, "Data folder is writable", str(exc))

    deno = shutil.which("deno")
    if deno:
        out = subprocess.run([deno, "--version"], capture_output=True, text=True, check=False)  # noqa: S603
        report(True, "Deno (needed by yt-dlp for YouTube)", out.stdout.split("\n")[0])
    else:
        report(False, "Deno (needed by yt-dlp for YouTube)", "not found on PATH")

    from echo_tunes.music import extract

    report(True, "yt-dlp", extract.version())

    async def music_checks() -> None:
        from echo_tunes.music.catalog import YTMusicCatalog

        try:
            track = await YTMusicCatalog(settings.language, settings.location).search_song(
                "never gonna give you up"
            )
            report(
                track is not None, "YouTube Music search", track.spoken if track else "no results"
            )
        except Exception as exc:
            report(False, "YouTube Music search", str(exc))

        try:
            t0 = time.monotonic()
            src = await asyncio.to_thread(
                extract.resolve, TEST_SONG, str(settings.ytdlp_cookies or ""), None
            )
            async with httpx.AsyncClient(timeout=15) as client:
                for _ in range(30):
                    resp = await client.get(
                        src["url"], headers={**src["headers"], "Range": "bytes=0-1023"}
                    )
                    if resp.status_code != 403:
                        break
                    await asyncio.sleep(0.3)
            ok = resp.status_code in (200, 206)
            report(
                ok,
                "Audio download from YouTube",
                f"{resp.status_code} after {time.monotonic() - t0:.1f}s"
                + ("" if ok else CLOUD_HINT),
            )
        except Exception as exc:
            report(False, "Audio download from YouTube", str(exc).splitlines()[0])

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{settings.base_url}/healthz")
            report(
                resp.status_code == 200,
                "Public URL reaches this server",
                f"{settings.base_url}/healthz answered {resp.status_code}",
            )
        except Exception as exc:
            report(False, "Public URL reaches this server", f"{type(exc).__name__}: {exc}")

    asyncio.run(music_checks())
    print("\nAll good." if not failures else f"\n{failures} check(s) failed.")
    sys.exit(1 if failures else 0)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="echo-tunes", description=__doc__)
    parser.add_argument("--version", action="version", version=f"echo-tunes {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the server (default)")
    sub.add_parser("doctor", help="check configuration, YouTube access and the public URL")
    args = parser.parse_args(argv)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    if args.command == "doctor":
        doctor()
    else:
        serve()
