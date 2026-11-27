"""Build the public site for GitHub Pages: the landing page and the web player demo.

The demo is the real, committed web player build (src/echo_tunes/web/dist, from `web/`) with
one meta tag added: it makes the app load its fake API (web/src/demo/demo-api.ts) instead of
talking to a server, so the demo always matches the real thing. No Node needed here.

    uv run python scripts/build_demo.py site     # then serve site/ and open /demo/
    uv run python scripts/build_demo.py site --demo-only   # just the demo (screenshots)
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "src" / "echo_tunes" / "web" / "dist"

SITE = "https://denzilrdz.github.io/echo-tunes/"
DEMO_HEAD = f"""<meta name="echo-tunes-demo" content="1" />
    <meta name="description" content="Try the echo-tunes web player with sample data: search and browse YouTube Music, pick an Echo or this phone, see what's playing everywhere, history, stats and setup checks." />
    <link rel="canonical" href="{SITE}demo/" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="echo-tunes" />
    <meta property="og:title" content="echo-tunes web player demo" />
    <meta property="og:description" content="The web player and dashboard of a self-hosted Alexa skill that plays YouTube Music: play here or on any Echo." />
    <meta property="og:url" content="{SITE}demo/" />
    <meta property="og:image" content="{SITE}img/social-preview.png" />
    <meta property="og:image:width" content="1280" />
    <meta property="og:image:height" content="640" />
    <meta name="twitter:card" content="summary_large_image" />
"""


def demo_page() -> str:
    html = (DIST / "index.html").read_text()
    replacements = [
        ("<title>echo-tunes</title>", "<title>echo-tunes web player demo</title>"),
        ('<meta name="robots" content="noindex" />\n', ""),
        # The install manifest and service worker belong to a real server, not the demo.
        ('    <link rel="manifest" href="/manifest.webmanifest" />\n', ""),
        ('<meta name="echo-tunes-accent" content="" />', DEMO_HEAD.rstrip()),
    ]
    for old, new in replacements:
        if old not in html:
            raise SystemExit(f"demo build: {old.strip()!r} missing; did web/index.html change?")
        html = html.replace(old, new, 1)
    if '"/' in html:
        raise SystemExit("demo build: an absolute path is left in index.html (Pages serves /demo/)")
    return html


def build(out: Path, demo_only: bool = False) -> None:
    if not (DIST / "index.html").is_file():
        raise SystemExit(f"demo build: {DIST} is missing; run `npm run build` in web/")
    if out.exists():
        shutil.rmtree(out)
    demo = out / "demo"
    shutil.copytree(DIST, demo, ignore=shutil.ignore_patterns("login.html", "sw.js"))
    (demo / "index.html").write_text(demo_page())
    if demo_only:  # scripts/screenshots.py: the landing page's images don't exist yet
        return

    # Landing page, images, and the files search engines look for.
    landing = (ROOT / "demo" / "landing.html").read_text()
    (out / "index.html").write_text(landing)
    shutil.copy(ROOT / "demo" / "landing.css", out / "landing.css")
    (out / "fonts").mkdir()
    [font] = sorted((DIST / "assets").glob("inter-latin-wght-normal-*.woff2"))
    shutil.copy(font, out / "fonts" / "inter-latin-wght.woff2")  # the app's own Inter
    img = out / "img"
    img.mkdir()
    # Every image the landing page refers to (and the social preview), so a new screenshot
    # can't go missing from the site: a reference to a file that doesn't exist fails the build.
    wanted = {"social-preview.png", *re.findall(r"img/([\w.-]+\.(?:png|svg))", landing)}
    for name in sorted(wanted):
        src = ROOT / "docs" / "img" / name
        if not src.is_file():
            raise SystemExit(f"demo build: landing page refers to img/{name}, not in docs/img")
        shutil.copy(src, img / name)
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}sitemap.xml\n")
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{SITE}</loc></url>\n  <url><loc>{SITE}demo/</loc></url>\n</urlset>\n"
    )
    (out / "404.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Not found · echo-tunes</title><link rel="stylesheet" href="/echo-tunes/landing.css">'
        '<body class="notfound"><main><h1>Nothing here.</h1>'
        f'<p><a href="{SITE}">echo-tunes</a> · <a href="{SITE}demo/">Web player demo</a></p>'
        "</main></body></html>\n"
    )
    (out / ".nojekyll").write_text("")
    print(f"built {out}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    build(Path(args[0] if args else "site"), demo_only="--demo-only" in sys.argv)
