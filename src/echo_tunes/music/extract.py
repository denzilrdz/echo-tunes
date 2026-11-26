"""Runs inside resolver worker processes: turns a YouTube video ID into a direct audio link.

yt-dlp is large and keeps internal state (player scripts, caches) that grows over time, so it
never runs in the main server process. Workers are recycled after a fixed number of jobs (see
``resolver.Resolver``), which hands any memory it accumulated back to the operating system.
"""

from __future__ import annotations

import time
import urllib.parse
from pathlib import Path
from typing import Any

# One YoutubeDL per worker process, reused across jobs so the player script is fetched once.
_ydl: Any = None

# Echo devices play AAC in an MP4 container (YouTube format 140, ~128 kbps); Opus/WebM won't play.
_FORMAT = "140/bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]"


def _client(cookies: str | None, cache_dir: str | None) -> Any:
    global _ydl
    if _ydl is None:
        import yt_dlp  # imported here so the server process never loads it

        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": _FORMAT,
            "skip_download": True,
            "cachedir": cache_dir or False,
            "js_runtimes": {"deno": {}},
        }
        if cookies and Path(cookies).exists():
            opts["cookiefile"] = cookies
        _ydl = yt_dlp.YoutubeDL(opts)
    return _ydl


def resolve(
    video_id: str, cookies: str | None = None, cache_dir: str | None = None
) -> dict[str, Any]:
    """Return ``{url, headers, size, mime, expires}`` for the video's AAC audio."""
    info = _client(cookies, cache_dir).extract_info(
        f"https://music.youtube.com/watch?v={video_id}", download=False
    )
    url = info["url"]
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    expires = int(query.get("expire", [0])[0]) or int(time.time()) + 3600
    return {
        "url": url,
        "headers": dict(info.get("http_headers") or {}),
        "size": info.get("filesize") or (int(query["clen"][0]) if "clen" in query else None),
        "mime": "audio/mp4",
        "expires": expires,
    }


def version() -> str:
    import yt_dlp.version

    return str(yt_dlp.version.__version__)
