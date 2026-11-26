"""Command line: ``echo-tunes serve`` runs the server, ``echo-tunes doctor`` checks the setup."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from pydantic import ValidationError

from echo_tunes import __version__
from echo_tunes.config import Settings


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

    from echo_tunes.app import build_services, create_app
    from echo_tunes.dashboard import create_dashboard

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

    async def run() -> None:
        services, closers = build_services(settings)
        servers = [
            uvicorn.Server(
                uvicorn.Config(
                    create_app(settings, services),
                    host=settings.host,
                    port=settings.port,
                    proxy_headers=True,
                    log_level=settings.log_level,
                    timeout_graceful_shutdown=5,
                    server_header=False,
                )
            )
        ]
        if settings.dashboard_port and services.dashboard:
            dash = create_dashboard(services.dashboard)
            servers.append(
                uvicorn.Server(
                    uvicorn.Config(
                        dash,
                        host=settings.dashboard_host,
                        port=settings.dashboard_port,
                        access_log=False,
                        log_level=settings.log_level,
                        timeout_graceful_shutdown=5,
                        server_header=False,
                    )
                )
            )
            logging.getLogger(__name__).info(
                "dashboard on port %d%s (keep this port private)",
                settings.dashboard_port,
                " with a password" if services.dashboard.password else "",
            )
        tasks = [asyncio.create_task(s.serve()) for s in servers]
        try:
            # When one server stops (Ctrl-C / SIGTERM is delivered to it), stop the other too.
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for s in servers:
                s.should_exit = True
            await asyncio.gather(*tasks, return_exceptions=True)
            for item in closers:
                close = getattr(item, "aclose", None) or getattr(item, "close", None)
                if close is not None:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result

    asyncio.run(run())


def doctor() -> None:
    """Run every check and print a list; exit 1 if anything failed."""
    from echo_tunes.checks import run_checks
    from echo_tunes.music import account, extract
    from echo_tunes.music.catalog import YTMusicCatalog

    print(f"echo-tunes {__version__} doctor\n")
    settings = _settings()
    client = account.load_client(
        settings.data_dir, settings.google_client_id, settings.google_client_secret
    )
    catalog = YTMusicCatalog(
        *account.make_client(settings.data_dir, settings.language, settings.location, client)
    )

    async def resolve(video_id: str) -> tuple[str, dict[str, str]]:
        raw = await asyncio.to_thread(
            extract.resolve, video_id, str(settings.ytdlp_cookies or ""), None
        )
        return raw["url"], raw["headers"]

    checks = asyncio.run(
        run_checks(
            settings, search=catalog.search_song, resolve=resolve, signed_in=catalog.signed_in
        )
    )
    marks = {"ok": "\u2713", "warn": "!", "fail": "\u2717", "info": "-"}
    for c in checks:
        print(f"  {marks[c.status]} {c.name}: {c.detail}")
        if c.hint and c.status != "ok":
            print(f"      {c.hint}")
    failed = sum(c.status == "fail" for c in checks)
    print("\nAll good." if not failed else f"\n{failed} check(s) failed.")
    sys.exit(1 if failed else 0)


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
