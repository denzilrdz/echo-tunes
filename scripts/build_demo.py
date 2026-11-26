"""Build the public dashboard demo for GitHub Pages.

Uses the real dashboard files from src/echo_tunes/web, plus demo/demo.js which answers the
page's API calls with sample data, so the demo always matches the real thing.

    uv run python scripts/build_demo.py site     # then open site/demo/index.html
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "src" / "echo_tunes" / "web"

BANNER = (
    '<div class="demo-banner" role="note">Demo with sample data: nothing plays and nothing '
    'is sent anywhere. <a href="https://github.com/denzilrdz/echo-tunes">Run your own '
    "echo-tunes</a></div>"
)
SITE = "https://denzilrdz.github.io/echo-tunes/"
DEMO_HEAD = f"""<meta name="description" content="Live demo of the echo-tunes dashboard with sample data: what each Echo is playing, play history, listening stats and the setup checklist.">
  <link rel="canonical" href="{SITE}demo/">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="echo-tunes">
  <meta property="og:title" content="echo-tunes dashboard demo">
  <meta property="og:description" content="Now playing, history, stats and setup checks for a self-hosted Alexa skill that plays YouTube Music.">
  <meta property="og:url" content="{SITE}demo/">
  <meta property="og:image" content="{SITE}img/social-preview.png">
  <meta property="og:image:width" content="1280">
  <meta property="og:image:height" content="640">
  <meta name="twitter:card" content="summary_large_image">
"""
CSS = """
.shots .demo-banner { display: none; }
.demo-banner { background: var(--warn-soft); color: var(--warn); text-align: center;
  padding: .5rem 1rem; font-size: .9rem; border-bottom: 1px solid var(--line); }
.demo-banner a { color: inherit; font-weight: 600; }
"""


def build(out: Path) -> None:
    demo = out / "demo"
    if out.exists():
        shutil.rmtree(out)
    demo.mkdir(parents=True)
    for name in ("app.js", "player.js", "app.css", "icon.svg", "apple-touch-icon.png"):
        shutil.copy(WEB / name, demo / name)
    shutil.copy(ROOT / "demo" / "demo.js", demo / "demo.js")
    (demo / "app.css").write_text((demo / "app.css").read_text() + CSS)

    html = (WEB / "index.html").read_text().replace("/static/", "")
    html = html.replace(
        '<script src="app.js" defer></script>',
        '<script src="demo.js"></script>\n  <script src="app.js" defer></script>',
    )
    html = html.replace(
        "<title>echo-tunes</title>", "<title>echo-tunes dashboard demo</title>\n  " + DEMO_HEAD
    )
    html = html.replace('<meta name="robots" content="noindex">\n', "")
    # The installable-app manifest and service worker belong to a real server, not the demo.
    html = html.replace('  <link rel="manifest" href="/manifest.webmanifest">\n', "")
    html = html.replace("<body>\n", "<body>\n  " + BANNER + "\n", 1)
    for needed in ('src="demo.js"', "demo-banner", 'href="app.css"', 'src="player.js"'):
        if needed not in html:
            raise SystemExit(f"demo build: {needed!r} missing; did index.html change?")
    (demo / "index.html").write_text(html)

    # Landing page, images, and the files search engines look for.
    shutil.copy(ROOT / "demo" / "landing.html", out / "index.html")
    img = out / "img"
    img.mkdir()
    for name in ("social-preview.png", "dashboard-light.png", "dashboard-dark.png"):
        shutil.copy(ROOT / "docs" / "img" / name, img / name)
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}sitemap.xml\n")
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{SITE}</loc></url>\n  <url><loc>{SITE}demo/</loc></url>\n</urlset>\n"
    )
    (out / "404.html").write_text(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>Not found · echo-tunes</title><p style="font:17px system-ui;text-align:center;'
        f'margin-top:20vh">Nothing here. <a href="{SITE}">echo-tunes</a> · '
        f'<a href="{SITE}demo/">dashboard demo</a></p>\n'
    )
    (out / ".nojekyll").write_text("")
    print(f"built {demo}")


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "site"))
