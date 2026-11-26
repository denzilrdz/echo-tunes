# Monitoring

echo-tunes gives your own tools everything they need. Use what you already run: Uptime Kuma,
Prometheus and Grafana, Home Assistant, or plain `curl`. The dashboard's **Monitoring** tab shows
these settings pre-filled with your addresses.

| Endpoint | Port | Use it for |
| --- | --- | --- |
| `GET /healthz` | public (8080) | "Is it up and reachable from the internet?" Always `200` while the server runs. |
| `GET /api/health` | private (8081) | "Is it actually working?" `200` + `"status": "ok"`, or `503` + `"status": "degraded"` |
| `GET /metrics` | private (8081) | Prometheus metrics |
| `GET /api/now` | private (8081) | What's playing, for dashboards and automations |

> [!NOTE]
> The private port answers to IP addresses, `localhost` and your public URL's name. If a tool
> reaches it by another host name (for example `http://homeserver:8081`), add that name to
> `ECHO_TUNES_DASHBOARD_HOSTS`, or use the IP address. This blocks DNS-rebinding attacks.

## Uptime Kuma

Two monitors cover everything:

1. **Public side**: type *HTTP(s)*, URL `https://<your public address>/healthz`, interval 60 s.
   Tells you when Amazon and your Echo can't reach the server (tunnel down, certificate,
   DNS...). Run it from outside your network if you can.
2. **Is it working**: type *HTTP(s) - Json Query*, URL `http://<server>:8081/api/health`
   (or your private dashboard address), JSON query `status`, expected value `ok`, interval 60 s.
   Goes down when YouTube stops serving audio (the usual sign that yt-dlp needs an update),
   or when the server is down.

If you set a dashboard password, also set `ECHO_TUNES_DASHBOARD_API_TOKEN` (e.g.
`openssl rand -hex 32`) and add it to the private monitor under *Headers*:

```json
{ "Authorization": "Bearer <your token>" }
```

The token skips the password checks, so many wrong passwords on your network can't make the
monitor fail. HTTP Basic Auth (user `admin`, the password) still works, but waits its turn
behind other password checks.

### What `/api/health` says

```json
{
  "status": "ok",
  "version": "0.2.0",
  "uptime_seconds": 5021,
  "memory_mb": 74.6,
  "youtube": "ok",
  "last_audio_ok": 1795700512.1,
  "last_audio_error": null,
  "last_error": "",
  "signed_in": false,
  "history_days": 15,
  "history_plays": 42
}
```

`youtube` is `ok` when the last audio link worked (or a failure is more than an hour old),
`failing` when the latest attempt failed (then `status` is `degraded` and `last_error` says
why), or `unknown` before the first song.

## Prometheus and Grafana

```yaml
scrape_configs:
  - job_name: echo-tunes
    scrape_interval: 30s
    static_configs:
      - targets: ["<server>:8081"]
    # With a dashboard password, use the API token (ECHO_TUNES_DASHBOARD_API_TOKEN):
    # authorization: { type: Bearer, credentials: <your token> }
```

### Metrics

| Metric | Type | Meaning |
| --- | --- | --- |
| `echo_tunes_build_info{version}` | info | Running version |
| `echo_tunes_start_time_seconds` | gauge | Start time (uptime = `time() - this`) |
| `echo_tunes_alexa_requests_total{type}` | counter | Verified Alexa requests: `LaunchRequest`, `IntentRequest`, `AudioPlayer`, `PlaybackController`, ... |
| `echo_tunes_alexa_rejected_total{reason}` | counter | Refused requests: `signature`, `certificate` (also: too many certificate downloads at once), `timestamp`, `wrong_skill`, `too_large`, `missing_signature`, `slow_body` (body not received within 10 s) |
| `echo_tunes_intents_total{intent}` | counter | Voice commands (`PlayIntent`, `AMAZON.NextIntent`, ...) |
| `echo_tunes_songs_started_total` | counter | Songs an Echo started |
| `echo_tunes_playback_failures_total` | counter | Songs an Echo couldn't play |
| `echo_tunes_streams_total{outcome}` | counter | Audio requests: `ok` (sent in full), `cut_short` (YouTube ended early), `client_gone`, `client_stalled` (stopped reading for 30 s, or read under 4 KB/s for a minute), `cut` (cut on purpose by the player's experimental *Skip now*), `too_many` (stream limit), `bad_link`, `youtube_error`, `range_error`, `error` |
| `echo_tunes_stream_bytes_total` | counter | Audio bytes relayed |
| `echo_tunes_resolve_seconds` | histogram | Time to get a song's audio link from YouTube |
| `echo_tunes_resolve_failures_total` | counter | Audio links that couldn't be fetched |
| `echo_tunes_youtube_music_errors_total` | counter | Failed YouTube Music searches/lookups |
| `echo_tunes_last_resolve_success_time_seconds` / `..._failure_...` | gauge | When audio last worked / failed |
| `echo_tunes_echos_known` / `echo_tunes_echos_playing` | gauge | Echos with a queue / playing now |
| `echo_tunes_history_plays`, `echo_tunes_history_retention_days` | gauge | History size and setting |
| `echo_tunes_youtube_music_signed_in` | gauge | 1 when signed in |
| `process_*`, `python_info` | | Memory, CPU, open files (Linux) |

Labels only ever take the fixed values listed above (never song titles or device IDs), so the
number of series stays constant.

### Useful queries and alerts

```promql
# Songs per hour
increase(echo_tunes_songs_started_total[1h])

# YouTube audio success rate over 15 minutes
1 - increase(echo_tunes_resolve_failures_total[15m])
  / clamp_min(increase(echo_tunes_resolve_seconds_count[15m]) + increase(echo_tunes_resolve_failures_total[15m]), 1)

# 95th percentile time to start a song
histogram_quantile(0.95, sum by (le) (rate(echo_tunes_resolve_seconds_bucket[1h])))

# Someone is probing /alexa (rejections per hour)
increase(echo_tunes_alexa_rejected_total[1h])
```

```yaml
# Prometheus alerting rule: YouTube audio is failing (yt-dlp probably needs an update)
- alert: EchoTunesAudioFailing
  expr: echo_tunes_last_resolve_failure_time_seconds > echo_tunes_last_resolve_success_time_seconds
  for: 15m
```

## Home Assistant

```yaml
rest:
  - resource: http://<server>:8081/api/now
    scan_interval: 15
    # With a dashboard password:
    # headers:
    #   Authorization: "Bearer <ECHO_TUNES_DASHBOARD_API_TOKEN>"
    sensor:
      - name: "echo-tunes now playing"
        value_template: >-
          {{ value_json.devices[0].current.title ~ ' – ' ~ value_json.devices[0].current.artist
             if value_json.devices else 'Nothing' }}
```

## Containers

The image has a Docker `HEALTHCHECK` (`/healthz` every 60 s), so Docker, Portainer, Beszel,
Dozzle and similar tools show it as healthy or unhealthy. Memory stays flat (about 80 MB for the
server, up to ~250 MB while yt-dlp workers run); the example compose files cap it at 512 MB.
