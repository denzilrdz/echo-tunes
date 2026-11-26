"""Regenerate the README/docs screenshots and the social preview image.

Uses the demo in screenshot mode (made-up songs, generated artwork: no real album art in the
repo), captures light and dark versions with headless Chrome, and compresses them to a
256-colour palette (like pngquant).

    uv run --with pillow python scripts/screenshots.py
    CHROME=/path/to/chrome uv run --with pillow python scripts/screenshots.py
"""

from __future__ import annotations

import functools
import http.server
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SHOTS = {  # name: (tab, height)
    "dashboard": ("now", 720),
    "history": ("history", 760),
    "stats": ("stats", 900),
    "setup": ("setup", 640),
}


def serve(directory: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *a: None  # type: ignore[method-assign]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def themed(site: Path, theme: str) -> Path:
    """A copy of the demo whose stylesheet always uses one theme."""
    out = site.parent / f"site-{theme}"
    shutil.copytree(site, out, dirs_exist_ok=True)
    css = out / "demo" / "app.css"
    text = css.read_text()
    block = re.compile(r"@media \(prefers-color-scheme: dark\) \{.*?\n\}\n", re.S)
    if theme == "light":
        text = block.sub("", text)
    else:
        text = text.replace("@media (prefers-color-scheme: dark)", "@media all")
    css.write_text(text)
    return out


def capture(url: str, path: Path, width: int, height: int, profile: Path) -> None:
    subprocess.run(  # noqa: S603
        [
            CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            f"--user-data-dir={profile}", f"--window-size={width},{height}",
            "--virtual-time-budget=6000", f"--screenshot={path}", url,
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip


def compress(src: Path, dst: Path) -> None:
    img = Image.open(src).convert("RGB")
    pal = img.quantize(
        colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG
    )
    pal.save(dst, optimize=True)
    print(f"{dst.relative_to(ROOT)}: {img.width}x{img.height}, {dst.stat().st_size // 1024} KB")


def main() -> None:
    if not Path(CHROME).exists():
        sys.exit(f"Chrome not found at {CHROME}; set CHROME=")
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        build = [sys.executable, str(ROOT / "scripts" / "build_demo.py"), str(work / "site")]
        subprocess.run(build, check=True, capture_output=True)  # noqa: S603
        for theme in ("light", "dark"):
            server, port = serve(themed(work / "site", theme))
            try:
                for name, (tab, height) in SHOTS.items():
                    raw = work / f"{name}-{theme}.png"
                    capture(
                        f"http://127.0.0.1:{port}/demo/?shots#{tab}",
                        raw,
                        1280,
                        height,
                        work / "prof",
                    )
                    compress(raw, OUT / f"{name}-{theme}.png")
            finally:
                server.shutdown()
        # Social preview (GitHub "Social preview" and og:image): 1280x640, dark.
        shutil.copy(ROOT / "demo" / "social.html", work / "site-dark" / "social.html")
        server, port = serve(work / "site-dark")
        try:
            raw = work / "social.png"
            capture(f"http://127.0.0.1:{port}/social.html", raw, 1280, 640, work / "prof")
            compress(raw, OUT / "social-preview.png")
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
