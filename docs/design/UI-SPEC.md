# echo-tunes web UI rewrite: spec

Owner's goals, in priority order:

1. **Mobile-first.** The app is controlled from a phone most of the time (installed PWA). Design
   the phone layout first; desktop is the enhancement. Thumb-reachable controls, bottom tab bar,
   mini-player above it that expands into a full-screen Now Playing sheet (swipe up/down),
   44-48 px touch targets, safe-area insets, fast perceived loading (skeletons), no layout shift.
2. **Favourite device, not "This browser" first.** The user picks a favourite play target (an
   Echo like "Living room", or this phone/browser). It is remembered per browser (localStorage),
   pre-selected every time the app opens, shown at all times on the mini-player ("Playing on
   Living room" strip/pill), switchable from a Spotify-Connect-style device sheet, and the
   favourite can be changed there ("☆ Make favourite"). First run: a friendly sheet asks
   "Where should music play?" listing the Echos (with what's playing/idle) and "This phone".
   If the favourite Echo is idle/offline (no recent activity): still selectable, with a clear
   note "Start it once by voice: 'Alexa, ask my tunes to play …'" since the web page can't start
   an idle Echo; offer "Play here instead" as a one-tap alternative.
3. **A new, premium design language from a clean slate** (do not keep the old dashboard's
   look/layout/tabs). Inspiration: Spotify, YouTube Music, Apple Music, Tidal, Plexamp, Sonos.
4. **The same design language on the public demo and the GitHub Pages landing page.**
5. **Fix the PWA's off theme colours.**

## Research findings (from a researched brief, 2026-11-26; verify versions with `npm view`)

### Why the PWA colours are off
`ECHO_TUNES_APP_COLOR` (#1f6feb blue) is written into `<meta name="theme-color">` (dashboard.py)
and the manifest `theme_color`, while `background_color` is hardcoded #0d1117. So status/title
bars are blue regardless of theme and the splash is near-black. Fix: theme_color and
background_color = the app background (#0B0B0F); per-scheme meta theme-color tags with `media`;
`ECHO_TUNES_APP_COLOR` only overrides the accent colour (`--accent`), never theme-color.
Safari 26 samples the html/body background and fixed/sticky elements instead of theme-color,
so `html, body { background: var(--bg) }` matters.

### Design principles
1. Artwork leads, the chrome recedes: neutral near-black/white UI; colour comes from artwork
   (tinted gradients behind album/playlist/artist headers and Now Playing). One brand accent
   (violet) for primary actions and active states only.
2. Always show where music will play: every play action names its target ("Play next on
   Living room"); device pill always visible (Spotify Connect pattern).
3. Honest capabilities: on an Echo the web page can't pause/previous (Alexa limitation; picks
   play after the current song). Show disabled controls with the reason ("Say 'Alexa, pause'"),
   never buttons that silently do nothing. First time an Echo is selected: one-time explainer
   ("Echo plays your picks after the current song. Use your voice to pause or go back." [Got it]).
4. Listening first, admin second: Home, Search, Library, Devices are the app; History, Stats,
   Status (monitoring), Setup, Settings live under "Server" (gear).
5. Feels instant: content-shaped skeletons, optimistic queue updates + toast, fixed-ratio art.
6. Restrained motion: 120-320 ms, colour crossfade on track change, sheet slide-up; honour
   prefers-reduced-motion (opacity-only, ≤120 ms).
7. Dark-first with a real light theme (system default, manual override in Settings); PWA
   chrome matches both.
8. Keyboard/a11y: every row action reachable by keyboard and context menu; toasts aria-live;
   AA contrast.

### IA
Primary nav (bottom tabs on mobile, sidebar on desktop): **Home** (home rows "Quick picks",
your mixes, charts, top artists, moods & genres chips; "Finish setup" banner only if checks
fail), **Search** (instant results ~250 ms debounce, filter chips All·Songs·Albums·Artists·
Playlists, Top result card + Songs in All view, recent searches in localStorage), **Library**
(signed-in playlists incl. Liked songs; sign-in empty state otherwise), **Devices** (one card
per target: This browser + each Echo, with art/title/progress/up next, capability badges
"Queue ✓", "Voice pause", "Skip now · beta", "Lock-screen controls", buttons "Play here" /
"Make favourite").
Secondary under **Server** (gear in Home header on mobile, bottom of sidebar on desktop):
Status (health tiles + copy-paste monitoring snippets), Stats, History, Setup (checklist +
test play), Settings (theme, sign out, favourite device, "Sign out everywhere" if available).

When an Echo is the target: primary button reads "Play next" (not "Play"); toast "Queued on
Living room · plays after 'Song X'"; pause/previous disabled with tooltip/aria-description;
with the experimental flag, Next becomes "Skip now (beta)".

### Mobile sketch
```
┌────────────────────────┐     ┌────────────────────────┐ (sheet, swipe ↓)
│ Good evening      ⚙    │     │ ⌄    Playing on        │
│ [chips: Relax Focus…]  │     │      Living room · Echo│
│ Quick picks            │     │ ┌────────────────────┐ │
│ ┌──┐ Song   ⋯          │     │ │      artwork       │ │
│ ┌──┐ Song   ⋯          │     │ └────────────────────┘ │
│ Your playlists  → ▢▢▢  │     │ Title            ♡     │
│ Charts          → ▢▢▢  │     │ Artist                 │
├────────────────────────┤     │ ━━━━━━●────── 1:02 3:41│
│[art] Title·Artist ⏯ 🔊 │mini │   ⏮(dim)  ⏯(dim)  ⏭   │
│▔▔▔ Playing on Living rm│     │ "Say 'Alexa, pause'"   │
├────────────────────────┤     │ [Up next ▴] [Devices]  │
│ ⌂    🔍    ▤     🔊    │     └────────────────────────┘
└────────────────────────┘
```
Mini-player above the tab bar with a 2 px progress line; tap/swipe up → full sheet (Drawer),
background = blurred artwork + extracted colour. "Up next" = half-height queue drawer. Device
picker = bottom drawer. env(safe-area-inset-*) padding.

### Desktop sketch (≥1024 px)
```
┌────────────┬──────────────────────────────────────────┬───────────────┐
│ ♪ echo     │  [🔍 Search songs, albums, artists   ⌘K] │ NOW PLAYING ▾ │
│ ⌂ Home     │  ▓▓▓ gradient from artwork ▓▓▓▓▓▓▓▓▓▓▓▓▓ │  artwork      │
│ 🔍 Search  │  ┌──────┐  PLAYLIST                      │ Title/Artist  │
│ ▤ Library  │  │ art  │  Chill Mix · 42 songs          │ Up next/Queue │
│ 🔊 Devices │  (▶ Play next on Living room)  ⇄  ⋯      │               │
│ PLAYLISTS… │  # Title            Artist      3:41  ⋯  │               │
│ ⚙ Server   │                                          │               │
├────────────┴──────────────────────────────────────────┴───────────────┤
│ [art] Title / Artist  ♡ │  ⏮ ⏯ ⏭  ━━━●──── 1:02/3:41 │ ☰ 🔊Living room ▾│
└───────────────────────────────────────────────────────────────────────┘
```
Album/playlist/artist page: hero (160-232 px cover; gradient from artwork colour fading to bg
over ~320 px), big round accent play button, dense track rows (48 px desktop, 56 px mobile)
with ⋯ menu (Play now / Play next / Add to queue / Start radio / Go to artist/album), context
menu on right-click. Artists round. Search: Top result card + 4 songs, then shelves. Empty
states everywhere. History: filters in URL search params, paginated table. Stats: KPI tiles,
hand-built SVG bar chart, top-10 lists. Status: health tiles with dots + code blocks with copy.
Sign-in: centred card on artwork-gradient background.

### Design tokens
| Token | Dark | Light |
|---|---|---|
| --bg | #0B0B0F | #FAFAFB |
| --surface | #141419 | #FFFFFF |
| --surface-2 | #1C1C23 | #F2F2F5 |
| --elevated | #23232B | #FFFFFF + shadow |
| --border | #2A2A33 | #E4E4E9 |
| --fg | #F4F4F6 | #111114 |
| --fg-muted | #A1A1AA | #5B5B66 |
| --accent | #A78BFA | #6D28D9 |
| --accent-fg | #0B0B0F | #FFFFFF |
| --success | #34D399 | #047857 |
| --warning | #FBBF24 | #B45309 |
| --danger | #F87171 | #B91C1C |
| --focus-ring | #C4B5FD | #7C3AED |
| --art (runtime) | #3B2F5E | #E9E3FB |
Art colour clamped in OKLCH: L 0.30-0.45 dark / 0.85-0.92 light, chroma ≤ 0.12. Hero gradient:
`linear-gradient(180deg, color-mix(in oklch, var(--art) 85%, var(--bg)) 0, var(--bg) 320px)`.
Radius 6/10/16 px, art 8 px (4 px ≤48 px), pills 9999. Spacing 4 px base; gutters 16/24/32.
Sidebar 264 px; right panel 320-400; player bar 80 px; mini-player 64 px.
Type: Inter Variable self-hosted (@fontsource-variable/inter, latin subset, font-display swap),
fallback system-ui; 12/13/14/16/20(600)/24(700)/32/48-56(800, -0.02em); tabular-nums for times.
Motion: 120 hover, 200 menus, 320 sheets, 450 art crossfade; ease-out cubic-bezier(0.2,0,0,1).
CSS transitions, no Motion/Framer. Dark mode: surface steps not shadows; sheet backdrop
blur(24px) with solid fallback.

### PWA manifest / meta (served by dashboard.py, generated from settings)
theme_color = background_color = #0B0B0F; display standalone (+ display_override
["window-controls-overlay","standalone"] only if the header handles env(titlebar-area-*));
id "/", start_url "/#/", scope "/", categories ["music","entertainment"], icons 192/512/
maskable-512/svg, screenshots (wide 1280x800 + narrow 750x1334, generated in ?shots mode with
made-up data) for the richer install UI, shortcuts Search/Devices. ECHO_TUNES_APP_NAME /
ECHO_TUNES_APP_ICON keep working; ECHO_TUNES_APP_COLOR now sets only the accent.
Head: viewport-fit=cover; theme-color meta for dark (#0B0B0F) and light (#FAFAFB) with media;
color-scheme "dark light"; apple-mobile-web-app-capable, mobile-web-app-capable,
apple-mobile-web-app-status-bar-style black-translucent (so pad env(safe-area-inset-top)),
apple-mobile-web-app-title, apple-touch-icon, manifest. A manual theme override updates the
theme-color meta content via setAttribute (fine under CSP).

### Stack (verify the CURRENT stable versions with `npm view <pkg> version`; pin exactly)
React 19 + TypeScript + Vite + Tailwind CSS v4 (@tailwindcss/vite) + shadcn/ui using the
**Base UI** flavour (`@base-ui/react`) + lucide-react; TanStack Router with hash history
(the Pages demo has no server fallback); TanStack Query (refetchInterval 3-5 s for devices/now
playing, paused when hidden); Zustand player store wrapping one HTMLAudioElement + queue +
Media Session; @tanstack/react-virtual only for long lists; vite-plugin-pwa with
injectRegister 'script' (never 'inline') OR a hand-written sw.js (must only cache the app
shell and hashed assets, never /api or /metrics); Vitest + Testing Library; Playwright smoke
test + CSP-violation check; Biome for lint/format. If any recommended package/version doesn't
exist or doesn't fit, pick the closest sound alternative and say so.

### CSP (must keep: script-src 'self'; style-src 'self'; no 'unsafe-inline')
- Blocked: <style> elements, style="" attributes in markup, setAttribute('style'), cssText.
  Allowed: CSSOM per-property (el.style.x = …, style.setProperty('--art', …)); React's
  client-side `style` prop uses CSSOM, so fine.
- AVOID: sonner, vaul, shadcn Chart (injects <style>), Radix Dialog/Popover (react-remove-scroll
  → react-style-singleton injects <style>), Radix Select/ScrollArea. Base UI: wrap in
  <CSPProvider disableStyleElements> and add `.base-ui-disable-scrollbar{scrollbar-width:none}`.
- Vite dev injects <style>; relaxed CSP only in dev.
- Production: hashed .css/.js files only. Add a Playwright test that fails on any
  `securitypolicyviolation` event under the real CSP header.

### Artwork colour
i.ytimg.com, lh3.googleusercontent.com (and very likely yt3.*) send
Access-Control-Allow-Origin: *. Use <img crossOrigin="anonymous">, draw the small thumbnail to a
24×24 (Offscreen)canvas, pick the dominant non-grey hue (fallback average), clamp per theme,
cache by id, set --art on the root via style.setProperty with a 450 ms crossfade; try/catch →
default --art.

### Build & supply chain
- Frontend project at repo root `web/` (package.json, package-lock.json committed, biome.json,
  vite.config.ts, .nvmrc, `.npmrc` with save-exact=true, ignore-scripts=true, engine-strict=true).
- Build output committed to `src/echo_tunes/web/` (served by dashboard.py) so wheel/sdist/Docker
  never need Node. Mark it `linguist-generated=true -diff` in .gitattributes.
- CI job: npm ci → lint → typecheck → test → build → `git diff --exit-code` on the committed
  output (deterministic builds), plus a bundle-size budget (initial JS ≤150 KB gzip, CSS ≤25 KB).
- Dependabot for npm (/web), weekly, cooldown 7 days (30 for majors), grouped minor/patch.
- Actions pinned by SHA with version comments, persist-credentials false, per-job permissions
  with comments, timeout-minutes, no `${{ }}` in run:. zizmor (auditor) + actionlint clean.
- Lazy-load Server pages; images lazy/async with explicit width/height; sized thumbnails.

## Landing page (GitHub Pages) in the same design language
Dark-first hero with an artwork-gradient glow, the logo, headline "YouTube Music on your Echo,
from your own server.", a short lead, CTAs "Try the demo" (primary) / "Set it up" / "GitHub",
a phone mockup screenshot of the mobile player next to a desktop screenshot, feature sections
(Ask by voice · Web player & phone app · Play on any Echo · Endless radio · Your library ·
Private & self-hosted · Secure by default), "How it works" 3 steps, FAQ, footer. Keep the
existing SEO tags (title/description/canonical/Open Graph/Twitter/JSON-LD/sitemap/robots/404)
and update their text/images. Social preview 1280×640 regenerated in the new style.
