<div align="center">

# echo-tunes

**YouTube Music on your Echo, from your own server.**
A private Alexa skill and web player you host yourself: one Docker container, no AWS account,
no Amazon password.

[![ci](https://github.com/denzilrdz/echo-tunes/actions/workflows/ci.yml/badge.svg)](https://github.com/denzilrdz/echo-tunes/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/denzilrdz/echo-tunes?include_prereleases&sort=semver)](https://github.com/denzilrdz/echo-tunes/releases)
[![image: amd64 + arm64](https://img.shields.io/badge/image-amd64%20%7C%20arm64-2496ed)](https://github.com/denzilrdz/echo-tunes/pkgs/container/echo-tunes)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/denzilrdz/echo-tunes/badge)](https://scorecard.dev/viewer/?uri=github.com/denzilrdz/echo-tunes)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[**Try the dashboard demo**](https://denzilrdz.github.io/echo-tunes/) ·
[Quick start](#quick-start) ·
[Setup guide](docs/SETUP.md) ·
[Public HTTPS options](docs/PUBLIC_HTTPS.md) ·
[Voice commands](docs/VOICE_COMMANDS.md) ·
[Google sign-in](docs/GOOGLE_SIGN_IN.md) ·
[Dashboard](docs/DASHBOARD.md) ·
[Monitoring](docs/MONITORING.md) ·
[How it works](docs/ARCHITECTURE.md) ·
[Troubleshooting](docs/TROUBLESHOOTING.md)

</div>

---

> **"Alexa, ask my tunes to play Blinding Lights."**
> Your Echo plays the song, then keeps going with a radio of similar songs. Next, previous,
> pause, resume, shuffle and loop all work by voice, and from the buttons in the Alexa app.
>
> **Or pick it yourself:** search and browse YouTube Music in the web player, play it in your
> browser, or line it up on any Echo. Add it to your phone's home screen and it's an app.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/player-dark.png" />
  <img src="docs/img/player-light.png" alt="The echo-tunes web player: search, your library, quick picks and trending playlists, with the player bar at the bottom" width="100%" />
</picture>

<sub>The web player ([live demo](https://denzilrdz.github.io/echo-tunes/demo/), sample data and made-up songs).</sub>

<table>
  <tr>
    <td width="50%"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/dashboard-dark.png" /><img src="docs/img/dashboard-light.png" alt="Now playing: what each Echo is playing and what's next" /></picture><br><sub><b>Now playing</b> on every Echo, and what's next</sub></td>
    <td width="50%"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/stats-dark.png" /><img src="docs/img/stats-light.png" alt="Stats: plays, listening time, top songs and artists" /></picture><br><sub><b>History and stats</b>, kept on your server</sub></td>
  </tr>
</table>

## Highlights

| Feature                | What you get                                                                                                      |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **One container**      | A single Docker image (amd64 and arm64: PCs, cloud servers, Raspberry Pi). No AWS Lambda, no database server.     |
| **No Amazon password** | You create a private skill in the free Alexa developer console. echo-tunes never sees your Amazon login.          |
| **Your own music**     | Optional Google sign-in: "play my liked songs", your playlists, your mixes, "like this song".         |
| **Endless radio**      | Every song starts a YouTube Music radio, and the queue tops itself up so the music doesn't stop.                  |
| **Fast song changes**  | The next song's audio is prepared while the current one plays.                                                   |
| **Runs anywhere**      | Any Docker host: a cloud server with a public IP, or a home server behind a tunnel. No vendor lock-in; ready examples for Caddy, Cloudflare Tunnel and Tailscale Funnel. |
| **Secure by default**  | Every request's Amazon signature and your skill ID are checked; audio links are signed and expire.                |
| **Flat memory**        | Bounded caches, streamed audio and recycled worker processes: memory doesn't creep up over weeks of uptime.       |
| **Web player**         | Search songs, albums, artists and playlists; browse charts, moods and your library. Play in the browser or queue on an Echo. [Demo](https://denzilrdz.github.io/echo-tunes/demo/) |
| **Phone app**          | Install the dashboard from your browser (it's a PWA): own icon, full screen, lock-screen controls. Name, colour and icon are settings. |
| **Private dashboard**  | Now playing and up next per Echo, 15-day play history (clear it any time), stats, a setup checklist and a "test play" button. |
| **Bring your own monitoring** | Prometheus `/metrics`, a JSON health check for Uptime Kuma, and a JSON API for Home Assistant.            |
| **Self-checking**      | `echo-tunes doctor` checks configuration, YouTube access and your public address in one go.                      |
| **Kept up to date**    | A daily job picks up new yt-dlp releases, so YouTube changes are fixed quickly.                                  |

> [!NOTE]
> **Early release.** Tested against real YouTube: voice playback, radio, queue top-up, next and
> previous, pause and resume, playback events and memory over long runs. Google sign-in and
> library playback (liked songs, playlists, mixes) are covered by automated tests but haven't
> been tried with many real accounts yet. Please
> [report problems](https://github.com/denzilrdz/echo-tunes/issues).

## Contents

- [How it compares](#how-it-compares)
- [What you need](#what-you-need)
- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Configuration](#configuration)
- [FAQ](#faq)
- [Roadmap](#roadmap)
- [Disclaimer](#disclaimer)

## How it compares

|                               | **echo-tunes**                    | Music Assistant + Alexa provider | Bluetooth from a phone |
| ----------------------------- | --------------------------------- | -------------------------------- | ---------------------- |
| Ask Alexa for a song by voice | ✅                                | ❌ (choose songs in its app)     | ❌                     |
| Needs your Amazon password    | ❌                                | ✅ (and a 2FA secret)            | ❌                     |
| Needs AWS / Lambda            | ❌                                | ❌                               | ❌                     |
| Moving parts                  | 1 container (+ your HTTPS tunnel) | Music Assistant + skill service  | A phone nearby         |
| Status                        | Early release                     | Experimental                     | Works today            |

There are other self-hosted YouTube-to-Alexa projects with more features (web remotes,
multiple users, podcasts). echo-tunes aims to be **the simple one**: a small codebase you can
read in an afternoon, set up in about 15 minutes, and then forget about.

## What you need

- **An Echo** (any model with a speaker) and the Amazon account it's registered to.
- **A free Amazon developer account** on that same Amazon account, to create your private skill.
- **A computer that's always on** with Docker: a home server, NAS, Raspberry Pi 4/5 or a cloud server.
- **A public HTTPS address** for it. Alexa only talks to HTTPS on port 443 with a trusted
  certificate. [Pick one of four ways](docs/PUBLIC_HTTPS.md); only the cloud-server option needs
  ports opened.

## Quick start

The full walkthrough is in **[docs/SETUP.md](docs/SETUP.md)**. In short:

**1. Run echo-tunes** on any always-on machine (home server, Raspberry Pi, VPS, AWS EC2...):

```bash
mkdir echo-tunes && cd echo-tunes
base=https://raw.githubusercontent.com/denzilrdz/echo-tunes/main
curl -fsSLO $base/compose.yaml
curl -fsSL $base/.env.example -o .env
# edit .env: ECHO_TUNES_PUBLIC_URL (and the skill ID after step 2)
docker compose up -d
```

Then give it a public HTTPS address. Alexa only needs `https://<your-address>/alexa` with a
trusted certificate; pick whichever fits ([details](docs/PUBLIC_HTTPS.md)):

| Your server | Ready-made setup | Open ports? |
| --- | --- | --- |
| Cloud server with a public IP (VPS, EC2...) | [Caddy](examples/caddy) (automatic Let's Encrypt) | 80, 443 |
| Home server, domain on Cloudflare | [Cloudflare Tunnel](examples/cloudflare-tunnel) | None |
| Home server, uses Tailscale | [Tailscale Funnel](examples/tailscale-funnel) | None |
| Already run nginx, Traefik or Caddy | Proxy your HTTPS site to `127.0.0.1:8080` | Yours |

Each example folder replaces `compose.yaml` above with one that includes the HTTPS part.

**2. Create your private skill** in the [Alexa developer console](https://developer.amazon.com/alexa/console/ask):
*Create skill* → name **echo tunes** → *Music & Audio* → *Custom* model → *Provision your own* hosting.
Paste the voice model from [`skill-package/`](skill-package/interactionModels/custom) into the
JSON editor, switch on the **Audio Player** interface, and set the endpoint to
`https://<your-public-address>/alexa`.

**3. Put the skill ID in `.env`**, restart, and check everything:

```bash
docker compose up -d
docker compose exec echo-tunes echo-tunes doctor
```

**4. Enable testing** (the skill's *Test* tab → *Development*) and say:
*"Alexa, ask my tunes to play Tum Hi Ho."*

**5. Optional: sign in** so you can say *"play my liked songs"* or *"play my playlist Road Trip"*:

```bash
docker compose exec -it echo-tunes echo-tunes login
```

See [docs/GOOGLE_SIGN_IN.md](docs/GOOGLE_SIGN_IN.md).

**6. Open the dashboard and player** on the private port, `http://localhost:8081` on the
server (or over an SSH tunnel, your LAN or a VPN; never the internet). Set
`ECHO_TUNES_DASHBOARD_PASSWORD` to play and queue songs from it, and open it over HTTPS to
install it on your phone. See [docs/DASHBOARD.md](docs/DASHBOARD.md).

## How it works

```mermaid
sequenceDiagram
    actor You
    participant Echo
    participant Alexa as Alexa cloud
    participant ET as echo-tunes (your server)
    participant YT as YouTube Music

    You->>Echo: "Alexa, ask my tunes to play Blinding Lights"
    Echo->>Alexa: voice
    Alexa->>ET: POST /alexa (signed request)
    ET->>ET: check Amazon signature, skill ID, timestamp
    ET->>YT: search + radio (ytmusicapi)
    ET-->>Alexa: "Playing Blinding Lights" + AudioPlayer.Play
    Echo->>ET: GET /stream/<signed link>.m4a
    ET->>YT: audio (yt-dlp link, relayed in chunks)
    ET-->>Echo: AAC audio
    Alexa->>ET: PlaybackNearlyFinished
    ET-->>Alexa: enqueue next song (already prepared)
```

More detail, including why audio is relayed and how memory is kept flat, is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Configuration

All settings are environment variables (or a `.env` file). Only the first two are required.

| Variable                               | Default    | Meaning                                                                     |
| -------------------------------------- | ---------- | --------------------------------------------------------------------------- |
| `ECHO_TUNES_PUBLIC_URL`                | (required) | Public HTTPS address of this server, e.g. `https://music.example.com`.      |
| `ECHO_TUNES_SKILL_IDS`                 | (required) | Your skill ID(s), comma-separated. Requests for other skills are refused.   |
| `ECHO_TUNES_LOCATION`                  | (empty)    | Two-letter country for search results: `US`, `GB`, `IN`, ...                |
| `ECHO_TUNES_LANGUAGE`                  | `en`       | Language for song and artist names.                                         |
| `ECHO_TUNES_RADIO_LENGTH`              | `25`       | Songs a radio adds at a time (5 to 50).                                     |
| `ECHO_TUNES_MAX_QUEUE`                 | `200`      | Longest queue kept per Echo (20 to 1000); played songs are dropped first.   |
| `ECHO_TUNES_GOOGLE_CLIENT_ID`          | (none)     | OAuth client for `echo-tunes login` (or type it in at login).               |
| `ECHO_TUNES_GOOGLE_CLIENT_SECRET`      | (none)     | Its secret.                                                                 |
| `ECHO_TUNES_SEND_HISTORY`              | `false`    | When signed in, add played songs to your YouTube history.                   |
| `ECHO_TUNES_YTDLP_COOKIES`             | (none)     | Path to a `cookies.txt` for yt-dlp, if YouTube blocks your server (must exist). |
| `ECHO_TUNES_RESOLVER_WORKERS`          | `2`        | Parallel workers that prepare audio links (1 to 8).                         |
| `ECHO_TUNES_RESOLVER_TASKS_PER_WORKER` | `25`       | Songs a worker prepares before a fresh one replaces it (1 to 1000; frees memory). |
| `ECHO_TUNES_STREAM_LINK_TTL_HOURS`     | `12`       | How long an audio link given to the Echo stays valid (1 to 48).             |
| `ECHO_TUNES_DASHBOARD_PORT`            | `8081`     | Private dashboard, `/metrics` and JSON API (`0` = off). Never publish it. |
| `ECHO_TUNES_DASHBOARD_HOST`            | `127.0.0.1` | Address the dashboard listens on (`0.0.0.0` in the Docker image, so its port can be published privately). |
| `ECHO_TUNES_DASHBOARD_HOSTS`           | (none)     | Extra host names you open the dashboard by, comma-separated, no port (e.g. `music-dash.lan`). |
| `ECHO_TUNES_DASHBOARD_PASSWORD`        | (none)     | Password for the dashboard (user `admin`); needed to play, queue and clear history from it. |
| `ECHO_TUNES_DASHBOARD_SESSION_DAYS`    | `180`      | Days a phone or browser stays signed in to the dashboard (`0` = until you sign out). |
| `ECHO_TUNES_DASHBOARD_API_TOKEN`       | (none)     | Bearer token (32+ random characters) for monitors and scripts; skips the password checks ([how](docs/MONITORING.md)). |
| `ECHO_TUNES_HISTORY_DAYS`              | `15`       | Days of play history to keep (`0` = keep none; up to 3650).                 |
| `ECHO_TUNES_DEVICE_NAMES`              | (none)     | Friendly Echo names: `BEWY4D23ORJQ=Living room,…` ([how](docs/DASHBOARD.md#naming-your-echos)). |
| `ECHO_TUNES_EXPERIMENTAL_SKIP`         | `false`    | Let the player try to skip the song playing on an Echo ([how it works](docs/DASHBOARD.md#player)). |
| `ECHO_TUNES_APP_NAME`                  | `echo-tunes` | Name of the installed phone app.                                          |
| `ECHO_TUNES_APP_COLOR`                 | `#1f6feb`  | Its theme colour (`#rrggbb`).                                               |
| `ECHO_TUNES_APP_ICON`                  | (built in) | Your own square PNG icon for it, e.g. `/data/icon.png`.                     |
| `ECHO_TUNES_LOG_LEVEL`                 | `info`     | `debug`, `info`, `warning`, `error` or `critical`.                          |
| `ECHO_TUNES_PORT`                      | `8080`     | Public port (Alexa and the Echo's audio).                                   |
| `ECHO_TUNES_HOST`                      | `0.0.0.0`  | Address the public port listens on.                                         |
| `ECHO_TUNES_DATA_DIR`                  | `./data`   | Where everything is stored (`/data` in the Docker image).                   |

Data (player queues, history, the key that signs audio links, your sign-in token, yt-dlp's
cache) lives in the data folder (`/data` in Docker); back it up and keep it private. Files are
created readable by the owner only.

## FAQ

**Do I need YouTube Premium?** No. Songs play without an account. Signing in (optional) only
adds your own library: liked songs, playlists and mixes.

**Are there ads?** echo-tunes plays the song's audio file directly, so nothing is inserted between songs.

**Can I just say "Alexa, play ..." without "ask my tunes"?** No. Amazon only lets its built-in
music services answer that; a private skill is always called by name. An Alexa routine can give
you a shorter phrase.

**Will it work on a cloud server?** Yes, but YouTube is much stricter with data-centre IP
addresses and may ask them to "sign in to confirm you're not a bot". A home server is the most
reliable. See [Troubleshooting](docs/TROUBLESHOOTING.md#youtube-blocks-a-cloud-server).

**Can my family use it?** Anyone using Echos on your Amazon account, yes. For other Amazon
accounts, invite them as beta testers of your skill in the developer console.

**Why not publish it in the Alexa Skill Store?** Amazon doesn't certify skills that play YouTube
content, so each person runs their own private copy. That's also why it's self-hosted.

## Roadmap

- [x] Voice playback, radio, queue, playback controls, Docker image, docs
- [x] Sign in with Google: your playlists, liked songs, mixes and personal radio
- [x] Private dashboard: now playing, history, stats, setup checklist and test play
- [x] Prometheus metrics and a health check for Uptime Kuma
- [ ] More languages for the voice model (German, Spanish, French, ...): contributions welcome

## Contributing

Bug reports and pull requests are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). For security
problems, please follow [SECURITY.md](SECURITY.md) instead of opening an issue.

## Disclaimer

echo-tunes is an independent project for personal use. It is not affiliated with, endorsed by
or sponsored by Amazon or Google. "Alexa", "Echo" and "YouTube Music" are trademarks of their
owners. It builds on the open-source [yt-dlp](https://github.com/yt-dlp/yt-dlp) and
[ytmusicapi](https://github.com/sigma67/ytmusicapi) projects. Using it may conflict with
YouTube's Terms of Service; you are responsible for how you use it.

## License

[MIT](LICENSE)
