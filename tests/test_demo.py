"""The GitHub Pages site is built from the committed web app build; make sure that keeps working."""

from __future__ import annotations

import re
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
    site = tmp_path / "site"
    html = (site / "demo" / "index.html").read_text()
    assert '<meta name="echo-tunes-demo" content="1"' in html  # selects the fake API
    assert "manifest.webmanifest" not in html and 'name="robots"' not in html
    assert not re.search(r'(src|href)="/', html), "absolute paths break under /demo/"
    for ref in re.findall(r'(?:src|href)="\./([^"]+)"', html):
        assert (site / "demo" / ref).is_file(), ref
    assert not (site / "demo" / "login.html").exists() and not (site / "demo" / "sw.js").exists()
    landing = (site / "index.html").read_text()
    for tag in ('property="og:image"', 'name="description"', 'rel="canonical"'):
        assert tag in landing, f"landing page lacks {tag}"
        assert tag in html, f"demo page lacks {tag}"
    assert "application/ld+json" in landing
    assert "<style" not in landing and " style=" not in landing  # same CSP rules as the app
    for name in ("robots.txt", "sitemap.xml", "404.html", "img/social-preview.png", "landing.css"):
        assert (site / name).exists(), name
