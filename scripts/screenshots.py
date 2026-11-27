"""Regenerate the README/docs screenshots, the social preview, the install screenshots and the
app icons.

Uses the demo in screenshot mode (?shots: made-up songs and generated artwork, so no real album
art or names end up in the repo), in light and dark, at phone and desktop sizes, and compresses
the PNGs to a 256-colour palette (like pngquant). Playwright (from web/) drives the browser.

    (cd web && npm ci && npm run build)          # the demo is the committed build
    uv run --with pillow python scripts/screenshots.py
    uv run --with pillow python scripts/screenshots.py --icons   # also re-render the icons

Writes docs/img/*.png, web/public/static/screenshot-{wide,narrow}.png (copied into the build
too, so no rebuild is needed) and, with --icons, web/public/static/icon-*.png.
"""

from __future__ import annotations

import functools
import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img"
WEB = ROOT / "web"
STATIC = WEB / "public" / "static"
BUILT = ROOT / "src" / "echo_tunes" / "web" / "dist" / "static"

PHONE = {"width": 390, "height": 844, "scale": 2, "mobile": True}
DESKTOP = {"width": 1280, "height": 800, "scale": 1}
# name: (demo URL after /demo/?shots, size, themes)
SHOTS: dict[str, tuple[str, dict[str, object], tuple[str, ...]]] = {
    "player-desktop": ("&target=browser#/", DESKTOP, ("dark", "light")),
    "player-mobile": ("#/", PHONE, ("dark", "light")),
    "now-playing-mobile": ("&sheet=now#/", PHONE, ("dark", "light")),
    "devices-mobile": ("&sheet=devices#/", PHONE, ("dark", "light")),
    "welcome-mobile": ("&sheet=welcome#/", PHONE, ("dark",)),
    "devices-desktop": ("#/devices", DESKTOP, ("dark",)),
    "collection-desktop": ("#/collection/playlist/playlist-Late-Night-Drive", DESKTOP, ("dark",)),
    "history": ("#/server/history", DESKTOP, ("dark", "light")),
    "stats": ("#/server/stats", DESKTOP, ("dark", "light")),
    "setup": ("#/server/setup", DESKTOP, ("dark", "light")),
}
# The install dialog's screenshots (manifest "screenshots"): exact sizes, dark.
INSTALL = {
    "screenshot-wide": ("&target=browser#/", {"width": 1280, "height": 800, "scale": 1}),
    "screenshot-narrow": ("#/", {"width": 375, "height": 667, "scale": 2, "mobile": True}),
}


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def serve(directory: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(_Quiet, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def capture(jobs: list[dict[str, object]]) -> None:
    subprocess.run(  # noqa: S603
        ["node", str(WEB / "scripts" / "capture.mjs")],  # noqa: S607
        input=json.dumps(jobs).encode(),
        cwd=WEB,
        check=True,
    )


def compress(src: Path, dst: Path) -> None:
    img = Image.open(src).convert("RGB")
    pal = img.quantize(
        colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG
    )
    pal.save(dst, optimize=True)
    print(f"{dst.relative_to(ROOT)}: {img.width}x{img.height}, {dst.stat().st_size // 1024} KB")


def icons(work: Path) -> None:
    """icon-192/512, the maskable icon (full bleed, art in the safe zone) and the Apple icon."""
    svg = (STATIC / "icon.svg").read_text()
    full = svg.replace('rx="15"', 'rx="0"')  # maskable/Apple: the OS rounds the corners
    maskable = full.replace("<path", '<g transform="translate(6.4 6.4) scale(.8)"><path', 1)
    maskable = maskable.replace("</svg>", "</g></svg>")
    jobs = []
    for name, size, art in (
        ("icon-192.png", 192, svg),
        ("icon-512.png", 512, svg),
        ("icon-maskable-512.png", 512, maskable),
        ("apple-touch-icon.png", 180, full),
    ):
        page = (
            "<!doctype html><style>html,body{margin:0;background:transparent}"
            f"svg{{display:block;width:{size}px;height:{size}px}}</style>{art}"
        )
        jobs.append(
            {"html": page, "out": str(work / name), "width": size, "height": size, "wait": 100}
            | {"transparent": True}
        )
    capture(jobs)
    for job in jobs:
        out = Path(str(job["out"]))
        Image.open(out).save(STATIC / out.name, optimize=True)
        shutil.copy(STATIC / out.name, BUILT / out.name)
        print(f"web/public/static/{out.name}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        if "--icons" in sys.argv:
            icons(work)
        build = [
            sys.executable,
            str(ROOT / "scripts" / "build_demo.py"),
            str(work / "site"),
            "--demo-only",
        ]
        subprocess.run(build, check=True, capture_output=True)  # noqa: S603
        server, port = serve(work / "site")
        try:
            base = f"http://127.0.0.1:{port}/demo/?shots"
            jobs: list[dict[str, object]] = []
            for name, (url, size, themes) in SHOTS.items():
                for theme in themes:
                    out = work / f"{name}-{theme}.png"
                    jobs.append(
                        {"url": f"{base}&theme={theme}{url}", "out": str(out), "scheme": theme}
                        | size
                    )
            for name, (url, size) in INSTALL.items():
                out = work / f"{name}.png"
                jobs.append(
                    {"url": f"{base}&theme=dark{url}", "out": str(out), "scheme": "dark"} | size
                )
            capture(jobs)
            for name, (_, _, themes) in SHOTS.items():
                for theme in themes:
                    compress(work / f"{name}-{theme}.png", OUT / f"{name}-{theme}.png")
            for name in INSTALL:
                compress(work / f"{name}.png", STATIC / f"{name}.png")
                shutil.copy(STATIC / f"{name}.png", BUILT / f"{name}.png")

            # Social preview (GitHub "Social preview" and og:image): 1280x640, dark.
            site = work / "site"
            shutil.copy(ROOT / "demo" / "social.html", site / "social.html")
            shutil.copy(ROOT / "demo" / "landing.css", site / "landing.css")
            (site / "fonts").mkdir()
            [font] = sorted((site / "demo" / "assets").glob("inter-latin-wght-normal-*.woff2"))
            shutil.copy(font, site / "fonts" / "inter-latin-wght.woff2")
            (site / "img").mkdir()
            for name in ("player-desktop-dark.png", "player-mobile-dark.png"):
                shutil.copy(OUT / name, work / "site" / "img" / name)
            raw = work / "social.png"
            capture(
                [
                    {
                        "url": f"http://127.0.0.1:{port}/social.html",
                        "out": str(raw),
                        "width": 1280,
                        "height": 640,
                    }
                ]
            )
            compress(raw, OUT / "social-preview.png")
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
