# Giving echo-tunes a public HTTPS address

Alexa has strict rules for skills hosted on your own server:

- the address must be **HTTPS on port 443**;
- the certificate must come from a **trusted certificate authority** (self-signed won't do);
- both Amazon's servers (for voice requests) **and your Echo** (for the audio) must reach it.

echo-tunes itself speaks plain HTTP on port 8080 and doesn't care what sits in front of it. Pick
one of these; each has a ready folder in [`examples/`](../examples).

| Option | Best for | Router ports to open | Your own domain needed |
| --- | --- | --- | --- |
| [Tailscale Funnel](#tailscale-funnel) | Home server on Tailscale | None | No (`*.ts.net`) |
| [Cloudflare Tunnel](#cloudflare-tunnel) | Home server, domain on Cloudflare | None | Yes |
| [Caddy](#caddy-on-a-server-with-a-public-ip) | VPS / AWS EC2 / any public IP | 80 and 443 | Yes (a free DuckDNS name works) |
| [Your own reverse proxy](#your-own-reverse-proxy) | You already run nginx/Traefik/Caddy | (already done) | Yes |

Whichever you pick, test from outside your network (e.g. phone on mobile data):

```bash
curl https://<your address>/healthz
```

---

## Tailscale Funnel

Funnel publishes one service from your tailnet to the internet at
`https://<machine>.<your-tailnet>.ts.net`, with a certificate Tailscale manages. Nothing else on
your network is exposed, and you don't touch your router.

**Before you start**, in the [Tailscale admin console](https://login.tailscale.com/admin):

1. *DNS* → enable **MagicDNS** and **HTTPS Certificates**.
2. *Access controls* → make sure your policy lets this machine use Funnel. The default policy
   has a `nodeAttrs` entry with `"attr": ["funnel"]`; if yours doesn't, add:
   ```json
   "nodeAttrs": [{ "target": ["autogroup:member"], "attr": ["funnel"] }]
   ```
3. *Settings → Keys* → **Generate auth key** (reusable off, ephemeral off). Copy it.

**Then**, using [`examples/tailscale-funnel`](../examples/tailscale-funnel):

```bash
cp .env.example .env                 # set ECHO_TUNES_PUBLIC_URL (see below) and the skill ID
echo "TS_AUTHKEY=tskey-auth-..." >> .env
docker compose up -d
```

The container joins your tailnet as `echo-tunes`, so the public address is
`https://echo-tunes.<your-tailnet>.ts.net` (the tailnet name is shown in the admin console under
*DNS*). Put that in `ECHO_TUNES_PUBLIC_URL` and run `docker compose up -d` again.

> [!TIP]
> **Already running Tailscale on the host?** You can skip the sidecar and run echo-tunes with
> the plain [`compose.yaml`](../compose.yaml), then on the host:
> `sudo tailscale funnel --bg --https=443 http://127.0.0.1:8080`. Your public address is then
> the host's `https://<host>.<tailnet>.ts.net`. Note this publishes port 443 of that host name,
> so don't use it if something else on the host already uses Funnel on 443.

## Cloudflare Tunnel

A tunnel connects out from your server to Cloudflare, which serves your domain with its
certificate. Needs a (free) Cloudflare account with your domain on it.

1. Cloudflare dashboard → *Zero Trust → Networks → Tunnels* → **Create a tunnel** →
   *Cloudflared* → name it `echo-tunes`. Copy the **token** from the install command.
2. In the tunnel's *Public hostnames*, add `music.yourdomain.com` → service **HTTP**
   `echo-tunes:8080`.
3. In [`examples/cloudflare-tunnel`](../examples/cloudflare-tunnel):
   ```bash
   cp .env.example .env              # ECHO_TUNES_PUBLIC_URL=https://music.yourdomain.com
   echo "TUNNEL_TOKEN=eyJh..." >> .env
   docker compose up -d
   ```

> [!IMPORTANT]
> Don't put Cloudflare Access (login pages) or "Bot Fight Mode" in front of this hostname:
> Amazon's servers and your Echo can't log in, so requests would be blocked.

## Caddy on a server with a public IP

For a VPS or cloud machine (AWS EC2, Lightsail, Hetzner, DigitalOcean, Oracle Cloud, ...).
Caddy fetches and renews a free Let's Encrypt certificate on its own.

1. Point a domain at the server's public IP (an `A` record). No domain? A free
   [DuckDNS](https://www.duckdns.org) name like `mymusic.duckdns.org` works.
2. Allow inbound **TCP 80 and 443** in the server's firewall / cloud security group
   (80 is only used to get the certificate).
3. In [`examples/caddy`](../examples/caddy):
   ```bash
   cp .env.example .env              # ECHO_TUNES_PUBLIC_URL=https://music.yourdomain.com
   echo "DOMAIN=music.yourdomain.com" >> .env
   docker compose up -d
   ```

> [!WARNING]
> YouTube treats requests from cloud providers' IP ranges with suspicion and may refuse them
> ("Sign in to confirm you're not a bot"). Run `echo-tunes doctor` after setup; if the
> *Audio download* check fails, see
> [Troubleshooting](TROUBLESHOOTING.md#youtube-blocks-a-cloud-server).

## Your own reverse proxy

Run echo-tunes with the plain [`compose.yaml`](../compose.yaml) (it listens on
`127.0.0.1:8080`) and add a site to your proxy. Requirements:

- forward everything (`/alexa`, `/stream/...`, `/healthz`) to `http://127.0.0.1:8080`;
- **don't buffer responses** (audio is streamed) and allow long-running responses (songs last minutes);
- pass the `Range` request header through (it is by default in all common proxies);
- don't add authentication in front of it.

nginx example:

```nginx
server {
    listen 443 ssl;
    server_name music.example.com;
    # ssl_certificate ... (e.g. from certbot)

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 1h;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```
