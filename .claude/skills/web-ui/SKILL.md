---
name: web-ui
description: The private dashboard, the GitHub Pages demo and landing page, and the docs screenshots. Use when changing src/echo_tunes/web/, dashboard.py routes the page uses, demo/, scripts/build_demo.py or scripts/screenshots.py, or regenerating docs/img.
---

# Web UI

## Dashboard (`src/echo_tunes/web/`)

- Plain HTML, CSS and one ES module (`app.js`); no build step, no framework, no CDN.
- CSP: `default-src 'self'`, no inline script or style; `media-src` adds the public origin
  (test play). Insert text with `textContent`, never `innerHTML` with data.
- Theme: CSS variables on `:root`, dark values under `@media (prefers-color-scheme: dark)`.
- Tabs are hash routes (`#now`, `#history`, `#stats`, `#monitor`, `#setup`).
- Time zone: stats send `tz` (minutes east of UTC) so days match the viewer's clock.
- Hooks for the demo: `window.ECHO_TUNES_DEMO` (fake API), `window.ECHO_TUNES_THUMB`
  (artwork URL builder).

## Demo and landing page (GitHub Pages)

- `uv run python scripts/build_demo.py site` builds `site/`: the landing page
  (`demo/landing.html`, with Open Graph, Twitter and JSON-LD tags), `demo/` (the real
  dashboard files + `demo/demo.js` sample data), `img/`, `robots.txt`, `sitemap.xml`, 404.
- `?shots` mode: made-up songs and generated SVG artwork, no banner. Never commit real album
  art or real song history.
- `.github/workflows/pages.yml` deploys on changes to these paths.

## Screenshots

`uv run --with pillow python scripts/screenshots.py` (needs Chrome; `CHROME=` to override):
light + dark per tab at 1280 px, palette-compressed to 256 colours, into `docs/img/`, plus
`social-preview.png` (1280×640, from `demo/social.html`). After regenerating, upload the
social preview in the repo settings (Settings → General → Social preview).
