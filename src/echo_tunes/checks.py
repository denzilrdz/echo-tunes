"""Setup checks, shared by ``echo-tunes doctor`` and the dashboard's Setup page."""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import httpx

from echo_tunes.config import Settings
from echo_tunes.music import extract
from echo_tunes.music.catalog import Track

TEST_SONG = "dQw4w9WgXcQ"  # long-lived and available everywhere; only used for self-tests
DOCS = "https://github.com/denzilrdz/echo-tunes/blob/main/docs/"


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str  # ok | warn | fail | info
    detail: str
    hint: str = ""
    link: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


Search = Callable[[str], Awaitable[Track | None]]
Resolve = Callable[[str], Awaitable[tuple[str, dict[str, str]]]]


async def run_checks(
    settings: Settings,
    *,
    search: Search,
    resolve: Resolve,
    signed_in: bool | None,
    last_alexa: float | None = None,
    password_set: bool | None = None,
) -> list[Check]:
    checks = [
        Check(
            "Configuration",
            "ok",
            f"Public address {settings.base_url}, {len(settings.skill_ids)} skill ID(s)",
        ),
        _data_folder(settings),
        await _deno(),
        _ytdlp(),
    ]
    checks.append(await _search(search))
    checks.append(await _audio(resolve))
    checks.append(await _public(settings.base_url))
    if last_alexa is not None:
        checks.append(_alexa(last_alexa))
    if signed_in is not None:
        checks.append(
            Check("YouTube Music account", "ok", "Signed in: your library is available", "")
            if signed_in
            else Check(
                "YouTube Music account",
                "info",
                "Not signed in (optional)",
                "Sign in for liked songs, playlists and mixes: echo-tunes login",
                DOCS + "GOOGLE_SIGN_IN.md",
            )
        )
    if password_set is False:
        checks.append(
            Check(
                "Dashboard password",
                "info",
                "No password: anyone who can reach this port can see what you play",
                "Fine if the port is only on your LAN or VPN; otherwise set "
                "ECHO_TUNES_DASHBOARD_PASSWORD",
                DOCS + "DASHBOARD.md",
            )
        )
    return checks


def _data_folder(settings: Settings) -> Check:
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.data_dir / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        return Check("Data folder", "ok", f"{settings.data_dir} is writable")
    except OSError as exc:
        return Check("Data folder", "fail", str(exc), "Check the volume's owner (uid 10001)")


async def _deno() -> Check:
    name = "Deno (JavaScript for yt-dlp)"
    deno = shutil.which("deno")
    if not deno:
        return Check(name, "fail", "not found", "Use the official Docker image")
    try:
        proc = await asyncio.create_subprocess_exec(
            deno, "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        async with asyncio.timeout(10):
            out, _ = await proc.communicate()
    except (TimeoutError, OSError) as exc:
        return Check(name, "fail", f"didn't answer: {type(exc).__name__}")
    return Check(name, "ok", out.decode(errors="replace").split("\n")[0])


def _ytdlp() -> Check:
    version = extract.version()
    try:
        released = date.fromisoformat(version[:10].replace(".", "-"))
        age = (date.today() - released).days
    except ValueError:
        return Check("yt-dlp", "ok", version)
    if age > 60:
        return Check(
            "yt-dlp",
            "warn",
            f"{version} ({age} days old)",
            "YouTube changes often; update echo-tunes to get a newer yt-dlp",
        )
    return Check("yt-dlp", "ok", f"{version} ({age} days old)")


async def _search(search: Search) -> Check:
    try:
        track = await search("never gonna give you up")
    except Exception as exc:
        return Check("YouTube Music search", "fail", _short(exc), "Is the internet reachable?")
    if track is None:
        return Check("YouTube Music search", "fail", "no results")
    return Check("YouTube Music search", "ok", f"found {track.spoken}")


async def _audio(resolve: Resolve) -> Check:
    t0 = time.monotonic()
    try:
        url, headers = await resolve(TEST_SONG)
        async with httpx.AsyncClient(timeout=15) as client:
            status = 0
            for _ in range(30):
                resp = await client.get(url, headers={**headers, "Range": "bytes=0-1023"})
                status = resp.status_code
                if status != 403:
                    break
                await asyncio.sleep(0.3)
    except Exception as exc:
        return Check(
            "Audio from YouTube",
            "fail",
            _short(exc),
            "On a cloud server YouTube may block the IP",
            DOCS + "TROUBLESHOOTING.md#youtube-blocks-a-cloud-server",
        )
    took = f"{time.monotonic() - t0:.1f}s"
    if status in (200, 206):
        return Check("Audio from YouTube", "ok", f"downloaded in {took}")
    return Check(
        "Audio from YouTube",
        "fail",
        f"YouTube answered {status}",
        "On a cloud server YouTube may block the IP",
        DOCS + "TROUBLESHOOTING.md#youtube-blocks-a-cloud-server",
    )


async def _public(base_url: str) -> Check:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base_url}/healthz")
        if resp.status_code == 200:
            return Check("Public address", "ok", f"{base_url}/healthz answered over HTTPS")
        return Check("Public address", "fail", f"answered {resp.status_code}")
    except Exception as exc:
        return Check(
            "Public address",
            "fail",
            f"{type(exc).__name__}: {_short(exc)}",
            "Amazon and your Echo must reach this address",
            DOCS + "TROUBLESHOOTING.md#the-public-address-doesnt-answer",
        )


def _alexa(last: float) -> Check:
    if not last:
        return Check(
            "Alexa has reached this server",
            "warn",
            "No request from Alexa since echo-tunes started",
            "Say “Alexa, ask my tunes to play …” (or use the console's Test tab)",
            DOCS + "TROUBLESHOOTING.md",
        )
    return Check("Alexa has reached this server", "ok", f"last request {_ago(last)}")


def _ago(t: float) -> str:
    s = int(time.time() - t)
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60} min ago"
    return f"{s // 3600} h ago"


def _short(exc: BaseException) -> str:
    text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    return text.split("http")[0].strip()[:200] or type(exc).__name__


def summary(checks: list[Check]) -> dict[str, Any]:
    worst = "ok"
    for c in checks:
        if c.status == "fail":
            worst = "fail"
        elif c.status == "warn" and worst == "ok":
            worst = "warn"
    return {"status": worst, "checks": [c.to_dict() for c in checks], "time": time.time()}
