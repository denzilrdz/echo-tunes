from __future__ import annotations

import subprocess
import sys


def test_checks_never_load_yt_dlp_into_the_server() -> None:
    """yt-dlp runs only in worker processes; the server (and its Setup page) must not import it."""
    code = (
        "import sys, asyncio\n"
        "from echo_tunes import checks\n"
        "from echo_tunes.music import extract\n"
        "extract.version(); checks._ytdlp(); asyncio.run(checks._deno())\n"
        "assert 'yt_dlp' not in sys.modules, 'yt_dlp was imported'\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603
