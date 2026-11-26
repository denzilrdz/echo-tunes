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
CSS = """
.demo-banner { background: var(--warn-soft); color: var(--warn); text-align: center;
  padding: .5rem 1rem; font-size: .9rem; border-bottom: 1px solid var(--line); }
.demo-banner a { color: inherit; font-weight: 600; }
"""


def build(out: Path) -> None:
    demo = out / "demo"
    if out.exists():
        shutil.rmtree(out)
    demo.mkdir(parents=True)
    for name in ("app.js", "app.css", "icon.svg"):
        shutil.copy(WEB / name, demo / name)
    shutil.copy(ROOT / "demo" / "demo.js", demo / "demo.js")
    (demo / "app.css").write_text((demo / "app.css").read_text() + CSS)

    html = (WEB / "index.html").read_text().replace("/static/", "")
    html = html.replace(
        '<script src="app.js" defer></script>',
        '<script src="demo.js"></script>\n  <script src="app.js" defer></script>',
    )
    html = html.replace("<title>echo-tunes</title>", "<title>echo-tunes dashboard demo</title>")
    html = html.replace('<meta name="robots" content="noindex">\n', "")
    html = html.replace("<body>\n", "<body>\n  " + BANNER + "\n", 1)
    for needed in ('src="demo.js"', "demo-banner", 'href="app.css"'):
        if needed not in html:
            raise SystemExit(f"demo build: {needed!r} missing; did index.html change?")
    (demo / "index.html").write_text(html)

    (out / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>echo-tunes</title>'
        '<meta http-equiv="refresh" content="0; url=demo/">'
        '<a href="demo/">echo-tunes dashboard demo</a>\n'
    )
    (out / ".nojekyll").write_text("")
    print(f"built {demo}")


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "site"))
