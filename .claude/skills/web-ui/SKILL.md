---
name: web-ui
description: The web player and dashboard (React app in web/, built into src/echo_tunes/web/dist), the GitHub Pages demo and landing page, and the screenshots. Use when changing web/, the pages or manifest dashboard.py serves, demo/, scripts/build_demo.py or scripts/screenshots.py, adding an npm package or UI component, or regenerating docs/img.
---

# Web UI

Design brief and owner priorities: `docs/design/UI-SPEC.md` (mobile first, favourite device,
artwork-led premium look, same language on the demo and landing page).

## Stack and layout (`web/`)

React 19 + TypeScript + Vite + Tailwind CSS 4 (`@tailwindcss/vite`) + Base UI (`@base-ui/react`,
shadcn/ui-style wrappers in `src/components/ui/`) + lucide-react; TanStack Router (hash
history: `#/search`, `#/server/stats`) and TanStack Query; Zustand stores; Biome; Vitest;
Playwright. Node from `web/.nvmrc`; `.npmrc` has save-exact, ignore-scripts, engine-strict.

```
web/index.html, login.html   two pages; placeholders the server fills (see "Server side")
web/public/                  copied as is: static/ (icons, boot.js, PWA screenshots), sw.js
web/src/main.tsx, login.tsx  entries; router.tsx: routes (Server pages lazy-loaded)
web/src/styles/app.css       tokens (CSS variables, dark + light), Inter @font-face, sheets
web/src/lib/                 api.ts (fetch, 401 -> /login, fake transport), queries.ts, art.ts
                             (thumbnails, cover colour), theme.ts, play.ts, storage.ts
web/src/store/               player.ts (target, favourite, the one <audio>, queue, radio,
                             Media Session, queueing on an Echo), ui.ts (sheets), toast.ts
web/src/components/          shell (sidebar/tab bar), player/ (bars, sheets, Now Playing
                             panel), music.tsx (cards, shelves, song rows), ui/
web/src/routes/              home, search, library (+ collection, mood), devices, server
web/src/demo/demo-api.ts     the Pages demo's fake API (own chunk)
web/e2e/                     Playwright smoke test + serve.mjs (static server with the CSP)
web/scripts/                 postbuild (relative paths, no-inline check), size budget, capture
```

Build output `src/echo_tunes/web/dist/` is committed (`linguist-generated`, `-diff`) and must
match the source: CI rebuilds and runs `git diff --exit-code`. Builds are deterministic.

## Rules

- **CSP** (`dashboard.csp()`): `script-src 'self'; style-src 'self'`, no `unsafe-inline`. No
  inline `<script>`, no `<style>` elements, no `style=""` in markup, no `setAttribute("style")`
  or `cssText`. React's `style` prop is fine (CSSOM), as is `el.style.setProperty("--x", ...)`.
  Fonts are files (`assetsInlineLimit: 0`); `font-src` falls back to `default-src 'self'`.
  `scripts/postbuild.mjs` fails the build on inline script/style in the HTML; `npm run e2e`
  fails on any `securitypolicyviolation`.
- **Text is text**: never `dangerouslySetInnerHTML` (Biome errors on it).
- **Tokens, not colours**: `bg-bg`, `bg-surface`, `bg-surface-2`, `bg-elevated`, `text-fg`,
  `text-fg-muted`, `border-border`, `bg-accent`/`text-accent-fg`, `text-success|warning|danger`.
  Dark values under `:root[data-theme="dark"]`. The accent comes from `ECHO_TUNES_APP_COLOR`
  via `--accent-custom`; theme-color stays the page background (#0B0B0F / #FAFAFB).
- **Artwork colour**: `useArtColour(url)` reads a 24×24 copy of the cover (CORS-enabled Google
  hosts), clamps it in OKLCH (dark L .30-.45, light L .85-.92, C ≤ .12) and sets `--art` on the
  element that needs it. Never on `:root`.
- **Honest controls**: on an Echo, play buttons read "Play next", pause/previous are disabled
  with the reason in their label, and an idle Echo offers "Play here instead".
- **Mobile first**: check 390×844 and 360×740 as well as 1280×800/1440×900, both themes; 44 px
  targets; `env(safe-area-inset-*)`; no sideways scrolling (the e2e test checks every page).
- **First download budget**: initial JS ≤ 150 KB gzip, CSS ≤ 25 KB (`npm run size`). Sheets,
  menus, Server pages and the demo API load on demand; keep it that way.

## Adding a component or package safely

1. Prefer Base UI primitives wrapped shadcn-style in `src/components/ui/` (copy the shadcn
   "base" variant by hand or `npx shadcn@<exact version> add <name>` into a scratch project,
   then adapt to our tokens). Don't use Base UI `Select` or `ScrollArea` (they inject
   `<style>`), Radix Dialog/Popover (react-remove-scroll), sonner, vaul or shadcn Chart.
2. `npm install --save-exact <pkg>@<version>` with a version at least a week old; check its
   code for `createElement("style")`, `innerHTML`, `cssText`, `eval`.
3. `npm run build && npm run size`, then `uv run python scripts/build_demo.py site` and
   `npm run e2e` (CSP and console errors), and look at it on a phone width.

## Server side (`dashboard.py`)

Serves `dist/index.html` at `/` and `dist/login.html` at `/login` through `page_html()` (fills
`<title>`, `application-name`, `apple-mobile-web-app-title`, `echo-tunes-accent`; keep those
placeholders in `web/*.html`), `/assets/*` (hashed, cached for a year), `/static/*`, `/sw.js`
(caches only `/`, `/login`, `/static/`, `/assets/`, the manifest; never `/api` or `/metrics`)
and `/manifest.webmanifest` from `manifest_json()`. `/assets/` and `/static/` are public (the
sign-in page needs them; no data in them).

## Demo, landing page, screenshots

- `uv run python scripts/build_demo.py site` builds `site/`: the landing page
  (`demo/landing.html` + `landing.css`, same tokens; SEO tags, JSON-LD, sitemap, robots, 404)
  and `site/demo/` = the committed build + `<meta name="echo-tunes-demo">`. No Node needed.
- `demo-api.ts` must answer every API path the app calls, POSTs included. `?shots`: made-up
  songs and generated SVG covers (never real album art or names in screenshots), a favourite
  Echo, `&target=browser` (a song playing here), `&sheet=now|devices|queue|welcome`,
  `&theme=light|dark`.
- `(cd web && npm run build)` then `uv run --with pillow python scripts/screenshots.py`
  (`--icons` also re-renders the PNG icons from `icon.svg`): Playwright (installed Chrome, or
  `PW_CHANNEL=chromium`) captures phone (390×844 @2x) and desktop (1280×800) shots in both
  themes into `docs/img/`, the PWA screenshots into `web/public/static/` (and the build), and
  `social-preview.png` (1280×640, `demo/social.html`), palette-compressed. Upload the social
  preview in the repo settings afterwards.
- `.github/workflows/pages.yml` deploys on changes to these paths.
