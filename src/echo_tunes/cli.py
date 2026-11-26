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
    # httpx logs every request URL at INFO; YouTube's links are long, signed and contain the
    # server's IP address, so keep them out of the logs unless debugging.
    if settings.log_level.lower() != "debug":
        for noisy in ("httpx", "httpcore"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
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
        from echo_tunes.music import account
        from echo_tunes.music.catalog import YTMusicCatalog

        method = account.signed_in_method(settings.data_dir)
        oauth_client = account.load_client(
            settings.data_dir, settings.google_client_id, settings.google_client_secret
        )
        try:
            catalog = YTMusicCatalog(
                *account.make_client(
                    settings.data_dir, settings.language, settings.location, oauth_client
                )
            )
            track = await catalog.search_song("never gonna give you up")
            report(
                track is not None, "YouTube Music search", track.spoken if track else "no results"
            )
            if method is None:
                print("  - YouTube Music account: not signed in (optional, see echo-tunes login)")
            elif method == "google" and oauth_client is None:
                report(False, "YouTube Music account", "signed in, but the OAuth client is missing")
            else:
                liked = await catalog.liked_songs()
                report(
                    True,
                    "YouTube Music account",
                    f"signed in ({method}); {len(liked.tracks)} liked songs readable",
                )
        except Exception as exc:
            report(False, "YouTube Music", f"{type(exc).__name__}: {exc}")

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


def login(use_browser: bool) -> None:
    """Sign in to YouTube Music (stores a token in the data folder)."""
    from echo_tunes.music import account

    settings = _settings()
    try:
        if use_browser:
            print(BROWSER_HELP)
            headers = sys.stdin.read()
            account.login_browser(settings.data_dir, headers)
        else:
            client = account.load_client(
                settings.data_dir, settings.google_client_id, settings.google_client_secret
            )
            if client is None:
                print(CLIENT_HELP)
                client = account.ClientSecrets(
                    input("Client ID: ").strip(), input("Client secret: ").strip()
                )

            def show(url: str, code: str) -> None:
                print(f"\n  1. On your phone or computer, open  {url}")
                print(f"  2. Enter the code                   {code}")
                print("  3. Choose your YouTube Music account and allow access.\n")
                print("Waiting for you to approve (Ctrl-C to cancel)...")

            account.login_device(settings.data_dir, client, show)
    except account.LoginError as exc:
        print(f"\nSign-in failed: {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)
    print("\nSigned in. Restart echo-tunes to use your library:  docker compose restart echo-tunes")


def logout() -> None:
    from echo_tunes.music import account

    removed = account.logout(_settings().data_dir)
    print("Signed out; restart echo-tunes." if removed else "Not signed in.")


CLIENT_HELP = """\
echo-tunes signs in with Google's TV-style sign-in, which needs your own (free) OAuth client.
Create one in a few minutes: docs/GOOGLE_SIGN_IN.md
(Google Cloud console > APIs & Services > Credentials > Create credentials > OAuth client ID >
"TVs and Limited Input devices", with the YouTube Data API v3 enabled.)

It's saved in the data folder, so you only enter it once. You can also set
ECHO_TUNES_GOOGLE_CLIENT_ID and ECHO_TUNES_GOOGLE_CLIENT_SECRET instead.
"""

BROWSER_HELP = """\
Paste the request headers of a signed-in music.youtube.com tab (docs/GOOGLE_SIGN_IN.md), then
press Enter and Ctrl-D:
"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="echo-tunes", description=__doc__)
    parser.add_argument("--version", action="version", version=f"echo-tunes {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the server (default)")
    sub.add_parser("doctor", help="check configuration, YouTube access and the public URL")
    p_login = sub.add_parser(
        "login", help="sign in to YouTube Music (for your playlists and likes)"
    )
    p_login.add_argument(
        "--browser",
        action="store_true",
        help="paste headers from a browser instead of Google sign-in",
    )
    sub.add_parser("logout", help="forget the YouTube Music sign-in")
    args = parser.parse_args(argv)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    if args.command == "doctor":
        doctor()
    elif args.command == "login":
        login(args.browser)
    elif args.command == "logout":
        logout()
    else:
        serve()
