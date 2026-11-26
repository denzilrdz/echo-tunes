"""The GitHub Pages demo is built from the real dashboard files; make sure that keeps working."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_demo_builds(tmp_path: Path) -> None:
    subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / "build_demo.py"), str(tmp_path / "site")],
        check=True,
        capture_output=True,
    )
    html = (tmp_path / "site" / "demo" / "index.html").read_text()
    assert html.index('src="demo.js"') < html.index('src="app.js"')
    assert "/static/" not in html and "demo-banner" in html
    for name in ("app.js", "app.css", "icon.svg", "demo.js"):
        assert (tmp_path / "site" / "demo" / name).exists(), name
    site = tmp_path / "site"
    landing = (site / "index.html").read_text()
    for tag in ('property="og:image"', 'name="description"', 'rel="canonical"'):
        assert tag in landing, f"landing page lacks {tag}"
        assert tag in html, f"demo page lacks {tag}"
    assert "application/ld+json" in landing
    for name in ("robots.txt", "sitemap.xml", "404.html", "img/social-preview.png"):
        assert (site / name).exists(), name
