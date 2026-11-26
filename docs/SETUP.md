# Setup guide

About 15 minutes, start to finish. You'll do four things:

1. [Give your server a public HTTPS address](#1-a-public-https-address)
2. [Start echo-tunes](#2-start-echo-tunes)
3. [Create your private Alexa skill](#3-create-your-private-alexa-skill)
4. [Connect them and test](#4-connect-and-test)

> [!TIP]
> Keep a text file open as you go. You'll collect two values: your **public address**
> (step 1) and your **skill ID** (step 3).

---

## 1. A public HTTPS address

Amazon's servers and your Echo must reach echo-tunes at an `https://` address on port 443 with
a real (trusted) certificate. Pick the option that fits your setup; each has a ready-made
folder in [`examples/`](../examples) and a walkthrough in [PUBLIC_HTTPS.md](PUBLIC_HTTPS.md).

| Your situation                                   | Use                                                                             | You get                                   |
| ------------------------------------------------ | ------------------------------------------------------------------------------- | ----------------------------------------- |
| Cloud server (VPS, AWS EC2, ...) with a public IP | [Caddy](PUBLIC_HTTPS.md#caddy-on-a-server-with-a-public-ip)                    | `https://music.yourdomain.com`            |
| Home server, have a domain on Cloudflare         | [Cloudflare Tunnel](PUBLIC_HTTPS.md#cloudflare-tunnel)                          | `https://music.yourdomain.com`            |
| Home server, already use Tailscale               | [Tailscale Funnel](PUBLIC_HTTPS.md#tailscale-funnel)                            | `https://echo-tunes.<tailnet>.ts.net`     |
| You already run nginx, Traefik or Caddy          | [Your own reverse proxy](PUBLIC_HTTPS.md#your-own-reverse-proxy)                | whatever you choose                       |

Write down the address, e.g. `https://music.example.com` or `https://echo-tunes.<tailnet>.ts.net`. This is your **public address**.

## 2. Start echo-tunes

Copy the example folder for your option to the server, then create the settings file:

```bash
cp .env.example .env
```

Edit `.env` and set your public address. Leave the skill ID as it is for now:

```bash
ECHO_TUNES_PUBLIC_URL=https://music.example.com
ECHO_TUNES_SKILL_IDS=amzn1.ask.skill.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
ECHO_TUNES_LOCATION=IN   # your country, for better search results
```

Start it and check the address works from outside:

```bash
docker compose up -d
curl https://music.example.com/healthz
# {"status":"ok","version":"0.1.0","memory_mb":74.2}
```

If that fails, see [Troubleshooting](TROUBLESHOOTING.md#the-public-address-doesnt-answer).

## 3. Create your private Alexa skill

Sign in to the **[Alexa developer console](https://developer.amazon.com/alexa/console/ask)**
with **the same Amazon account your Echo uses** (creating a developer account is free).

1. **Create skill.**
   - *Skill name*: `echo tunes` (only shown in the console; you'll say **"my tunes"**, because
     Amazon doesn't allow wake words like "Echo" or "Alexa" in the spoken name)
   - *Primary locale*: the language your Echo is set to. Check it in the Alexa app under
     *Devices → your Echo → Language*. "English (India)" is `en-IN`, "English (US)" is `en-US`, and so on.
   - *Type of experience*: **Music & Audio**
   - *Model*: **Custom**
   - *Hosting*: **Provision your own**
   - *Template*: **Start from scratch**
2. **Paste the voice model.** In *Build → Interaction Model → JSON Editor*, replace everything
   with the contents of the matching file from
   [`skill-package/interactionModels/custom/`](../skill-package/interactionModels/custom)
   (e.g. `en-IN.json`), then click **Save**.
3. **Turn on audio.** *Build → Interfaces* → switch on **Audio Player** → **Save**.
4. **Set the endpoint.** *Build → Endpoint* → **HTTPS**:
   - *Default Region*: `https://<your public address>/alexa`
   - Certificate: **"My development endpoint has a certificate from a trusted certificate authority"**
   - **Save**.
5. **Copy the skill ID.** It's shown at the top of the *Endpoint* page (`amzn1.ask.skill.…`).
6. **Build the model.** Click **Build skill** (top right) and wait for "Build successful".

> [!NOTE]
> Want both English (India) and English (US) on different Echos? Add each language under
> *Language settings* and paste the same model into each.

<details>
<summary>Prefer the command line? Deploy the skill with the ASK CLI instead</summary>

```bash
npm install -g ask-cli
ask configure                     # sign in to your Amazon developer account
sed -i 's#https://YOUR-PUBLIC-URL#https://music.example.com#' skill-package/skill.json
ask deploy                        # creates the skill from skill-package/
```

The skill ID is printed at the end and saved in `.ask/ask-states.json`.
</details>

## 4. Connect and test

Put the skill ID in `.env`:

```bash
ECHO_TUNES_SKILL_IDS=amzn1.ask.skill.1a2b3c4d-....
```

Restart and run the self-check:

```bash
docker compose up -d
docker compose exec echo-tunes echo-tunes doctor
```

```text
  ✓ Configuration: public URL https://music.example.com, 1 skill ID(s)
  ✓ Data folder is writable: /data
  ✓ Deno (needed by yt-dlp for YouTube): deno 2.9.8
  ✓ yt-dlp: 2026.11.23
  ✓ YouTube Music search: Never Gonna Give You Up by Rick Astley
  ✓ Audio download from YouTube: 206 after 3.1s
  ✓ Public URL reaches this server: https://music.example.com/healthz answered 200

All good.
```

Finally, in the developer console open the **Test** tab and set *Skill testing is enabled in*
to **Development**. The skill is now live on every Echo on your account. Try:

> "Alexa, ask my tunes to play Tum Hi Ho."

See [all voice commands](VOICE_COMMANDS.md).

## Optional: your own music

Sign in to YouTube Music to say *"play my liked songs"*, *"play my playlist …"* or
*"play my supermix"*: see [GOOGLE_SIGN_IN.md](GOOGLE_SIGN_IN.md).

## Updating

```bash
docker compose pull && docker compose up -d
```

New releases mostly carry yt-dlp updates that keep YouTube working. Watch the repository's
releases (*Watch → Custom → Releases*) or use a tool like Diun to be notified.
