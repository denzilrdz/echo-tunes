# Dashboard

A private web page that shows what your Echos are doing:

| Tab | What you see |
| --- | --- |
| **Now playing** | Each Echo's song with artwork and a live progress bar, why it's playing ("Asked for …", "Radio after …", "Playlist: …"), shuffle/loop, and the next 10 songs. Playing Echos come first. |
| **History** | Every song played in the last 15 days (configurable): when, which Echo, why, how long it was listened to, and whether it finished, was skipped, paused or failed. Filter by Echo and period, search by song or artist. |
| **Stats** | Plays, listening time, different songs and artists, plays per day, top songs and top artists, for a chosen period and Echo. |
| **Monitoring** | Health at a glance, plus copy-ready settings for Uptime Kuma, Prometheus and Home Assistant ([MONITORING.md](MONITORING.md)). |
| **Setup** | The same checklist as `echo-tunes doctor` (configuration, YouTube, your public address, "has Alexa reached this server?"), and a **Test play** button that plays a song in your browser through YouTube, this server and your public address, exactly like an Echo. |

The dashboard is **read-only**: nothing on it can change what plays.

It only answers to IP addresses, `localhost`, your public URL's name and names listed in
`ECHO_TUNES_DASHBOARD_HOSTS`, and refuses background requests from other websites. That stops
a malicious web page from reading it through your browser (DNS rebinding).

## Where it is

It runs on a **second port, 8081**, separate from the public port 8080 that Amazon and your Echo
use. Your HTTPS tunnel or reverse proxy only forwards the public port, so the dashboard stays
private as long as you don't publish 8081 to the internet yourself.

| Setup | Open the dashboard at |
| --- | --- |
| Plain `compose.yaml` | `http://localhost:8081` on the server (or `ssh -L 8081:localhost:8081 server` and open it on your computer) |
| [Tailscale Funnel example](../examples/tailscale-funnel) | `https://echo-tunes.<your-tailnet>.ts.net:8443`, **from your tailnet only** (Tailscale Serve, not Funnel) |
| [Cloudflare Tunnel](../examples/cloudflare-tunnel) / [Caddy](../examples/caddy) | `http://localhost:8081` on the server or over SSH; don't add a public hostname for it |

> [!WARNING]
> Never route port 8081 through Funnel, a Cloudflare public hostname or a public reverse proxy
> without a password: it shows what you listen to. If you need it on a shared network, set
> `ECHO_TUNES_DASHBOARD_PASSWORD` (the browser then asks for user `admin` and that password;
> it applies to `/metrics` and the JSON API too).

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `ECHO_TUNES_DASHBOARD_PORT` | `8081` | Port of the dashboard, `/metrics` and the JSON API. `0` turns it off. |
| `ECHO_TUNES_DASHBOARD_HOST` | `127.0.0.1` (`0.0.0.0` in the Docker image) | Address it listens on. The image listens on all interfaces so the port can be published; publish it privately. |
| `ECHO_TUNES_DASHBOARD_HOSTS` | (none) | Extra host names you open it by, comma-separated (e.g. `music-dash.lan`). IP addresses, `localhost` and your public URL's name always work; other names are refused. |
| `ECHO_TUNES_DASHBOARD_PASSWORD` | (none) | Optional password (HTTP Basic, user `admin`). |
| `ECHO_TUNES_HISTORY_DAYS` | `15` | Days of play history to keep. `0` keeps none (and deletes what's there). |
| `ECHO_TUNES_DEVICE_NAMES` | (none) | Friendly names, e.g. `BEWY4D23ORJQ=Living room,A6TA55XMCKTY=Kitchen`. |

### Naming your Echos

Alexa only tells a skill a long, random device ID. The dashboard shows its last 12 characters
(for example *Echo …4D23ORJQ*). Copy that from the Now playing tab or the History Echo filter and
set `ECHO_TUNES_DEVICE_NAMES=BEWY4D23ORJQ=Living room`, then restart.

## History and privacy

- Stored in `history.sqlite3` in the data folder: song, artist, which Echo, when, why, how long.
- Rows older than `ECHO_TUNES_HISTORY_DAYS` are deleted automatically (checked hourly and at
  start), so the file stays small: about 1 KB per song played.
- Nothing is sent anywhere. Artwork is loaded by your browser from YouTube's image server
  (`i.ytimg.com`), like on YouTube itself.

## JSON API

Everything the page shows comes from read-only JSON endpoints on the same port, handy for
scripts and home automation:

| Endpoint | Returns |
| --- | --- |
| `GET /api/now` | Each Echo: current song, position, playing/paused, source, next 10 songs |
| `GET /api/history?days=7&device=…&q=…&limit=50&offset=0` | Plays, newest first |
| `GET /api/stats?days=7&device=…` | Totals, plays per day, top songs and artists |
| `GET /api/devices` | Known Echos (ID tail and name) |
| `GET /api/health` | Health summary (see [MONITORING.md](MONITORING.md)) |
| `GET /api/setup` | The setup checklist (cached for a minute) |
| `GET /metrics` | Prometheus metrics |
