# Troubleshooting

Start with the self-check. It tests each link in the chain and says which one is broken:

```bash
docker compose exec echo-tunes echo-tunes doctor
```

Then look at the logs while you try again:

```bash
docker compose logs -f echo-tunes
```

---

## Alexa says "There was a problem with the requested skill's response"

- **No request in the logs at all:** Alexa can't reach your server. Check the endpoint in the
  developer console is exactly `https://<your address>/alexa`, and see
  [the public address doesn't answer](#the-public-address-doesnt-answer).
- **`rejected a request to /alexa: request is for a different skill`:** the skill ID in `.env`
  doesn't match. Copy it again from the console's *Endpoint* page and restart.
- **`rejected … request is too old`:** your server's clock is wrong. Make sure it syncs time
  (`timedatectl` should say *System clock synchronized: yes*).
- **`rejected … certificate not trusted`:** usually also the server clock. Otherwise please
  open an issue with the log line.

## Alexa answers but no music plays

- Alexa says *"Playing …"* and then nothing: the Echo couldn't load the audio. Look for
  `stream …` lines in the logs.
  - `YouTube refused the audio (403)`: see [YouTube blocks a cloud server](#youtube-blocks-a-cloud-server).
  - No `stream` line at all: the Echo can't reach your address. Echos need the public
    address to work **from inside your home network** too. Some routers don't support
    "hairpin" connections to their own public IP; tunnels (Tailscale Funnel, Cloudflare)
    avoid this.
- **Pi-hole or another DNS blocker?** Make sure it doesn't block your public address or
  `*.googlevideo.com` for the server.

## "Alexa, ask my tunes …" isn't recognised

- The skill only exists in the languages you added. If your Echo is set to *English (India)*,
  the skill needs the `en-IN` model (developer console → *Language settings*).
- Testing must be enabled: console → *Test* tab → *Development*.
- The developer account must be the same Amazon account as the Echo (or invite the other
  account as a beta tester).
- Try *"Alexa, open my tunes"* first; if that works, the invocation is fine and the song
  phrase wasn't understood. See [voice command tips](VOICE_COMMANDS.md#tips).

## The public address doesn't answer

From a phone **on mobile data** (outside your network):

```bash
curl -v https://<your address>/healthz
```

- **Tailscale Funnel:** run `tailscale funnel status` on the host (or `docker compose exec
  tailscale tailscale funnel status`). Funnel must be allowed in your tailnet policy, and
  MagicDNS + HTTPS certificates must be on. New Funnel addresses can take a few minutes to
  appear in public DNS.
- **Cloudflare Tunnel:** the tunnel must show *Healthy* in the dashboard, and the public
  hostname must point to `http://echo-tunes:8080`. Turn off Access policies and Bot Fight Mode
  for that hostname.
- **Caddy:** ports 80 and 443 must be open in the cloud firewall, and the domain must point at
  the server. `docker compose logs caddy` shows certificate errors.

## YouTube blocks a cloud server

On cloud servers (AWS, Google Cloud, Azure, Oracle, Hetzner, …) YouTube often answers
*"Sign in to confirm you're not a bot"* or `403`. In order of effort:

1. **Run echo-tunes at home** instead and reach it through a tunnel. Home internet addresses
   are rarely blocked.
2. **Give yt-dlp cookies** from a YouTube session: export `cookies.txt` with a browser extension
   while signed in to YouTube in a private window, put it in the `data` folder, and set
   `ECHO_TUNES_YTDLP_COOKIES=/data/cookies.txt`. Use a spare Google account, not your main one.
3. See yt-dlp's guide to
   [PO tokens](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide) for advanced options.

## Songs stop working after a while

YouTube changes things every few weeks, and yt-dlp releases a fix within days. Update:

```bash
docker compose pull && docker compose up -d
```

If the latest release still fails, please [open an issue](https://github.com/denzilrdz/echo-tunes/issues)
with the `doctor` output.

## The dashboard says it can't reach the server

The web player shows *Can't reach your echo-tunes server* when its requests get no answer at
all. It keeps what's on screen, turns playing off, and tries again by itself (after 10 s, then
less often) until the server answers.

- **Away from home:** connect to the network or VPN your server is on. The dashboard port is
  private on purpose.
- **At home but still failing:** the browser or phone is probably using its own "secure DNS"
  or "Private DNS" provider, which skips your network's DNS. If your dashboard's name only
  resolves to the server's LAN address through your router or local DNS (Pi-hole, AdGuard
  Home, a split-horizon setup), that provider answers with the public address instead, where
  the dashboard isn't served. Let that device use your network's DNS:
  - **Chrome / Edge (desktop and Android):** Settings › Privacy and security › Security › Use
    secure DNS → *With your current service provider* (or off).
  - **Android:** Settings › Network › Private DNS → *Automatic* or *Off*.
  - **iPhone / iPad:** turn off iCloud Private Relay for your home Wi-Fi (Settings › Wi-Fi › ⓘ
    › Limit IP Address Tracking / Private Relay), and remove DNS profiles or apps that set
    their own DNS.
  - Or open the dashboard by the server's IP address to check that this is the cause.
- **The server may be restarting or down:** check its status page or your monitoring
  ([MONITORING.md](MONITORING.md)), or `docker compose logs`.

## Getting help

[Open an issue](https://github.com/denzilrdz/echo-tunes/issues/new/choose) with:

- the output of `echo-tunes doctor` (it contains no secrets);
- the log lines around the problem (`docker compose logs --since 10m echo-tunes`);
- how you host it (Funnel, Cloudflare, Caddy, other) and your Echo model and language.
