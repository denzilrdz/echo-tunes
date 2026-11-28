# Sign in with Google (optional)

Without signing in, echo-tunes plays anything on YouTube Music and builds radios from it.
Signing in adds **your** music:

| Say "Alexa, ask my tunes to …" | Plays |
| --- | --- |
| "… play my liked songs" | Your liked songs (up to 200) |
| "… play my playlist Road Trip" | A playlist from your library (names don't have to be exact) |
| "… play my supermix" / "… play my discover mix" | Your personal mixes from the YouTube Music home page |
| "… like this song" | Adds the current song to your liked songs |

Radio and search results also become personal, based on your listening.

> [!NOTE]
> **What your account is used for:** only YouTube Music browsing (search, radio, your library,
> likes). The audio itself is always fetched **without** your account, so it's never involved
> in downloading. Optionally, echo-tunes can add what you play to your YouTube history so your
> recommendations keep learning: set `ECHO_TUNES_SEND_HISTORY=true`.

There are two ways to sign in. Both run **on the server** (there's deliberately no sign-in web
page, because the server is reachable from the internet).

| | [Google sign-in (recommended)](#google-sign-in) | [Browser headers](#browser-headers-quicker-less-durable) |
| --- | --- | --- |
| One-time setup | ~10 min: create a free Google Cloud OAuth client | ~2 min |
| How you sign in | Type a code at google.com/device on your phone | Copy headers from your browser's developer tools |
| Lasts | Until you revoke it (refreshes itself) | Until you sign out of that browser session |

---

## Google sign-in

### 1. Create your own OAuth client (once)

Google requires each app that signs in to YouTube to have its own client. It's free.

1. Open the [Google Cloud console](https://console.cloud.google.com) and **create a project**
   (top bar → project picker → *New project*), e.g. `echo-tunes`.
2. **Enable the YouTube Data API:** *APIs & Services → Library* → search
   **YouTube Data API v3** → **Enable**. Don't skip this: without it YouTube Music rejects the
   sign-in ("HTTP 400: Request contains an invalid argument"), although Google signs you in fine.
3. **Set up the consent screen:** *Google Auth Platform* (called *OAuth consent screen* in
   older consoles) → **Get started**.
   - *App name*: `echo-tunes`; *User support email*: yours.
   - *Audience*: **External**.
   - *Contact information*: your email → **Create**.
4. **Publish it**, so your sign-in doesn't expire every 7 days: *Audience* → **Publish app** →
   *Confirm*. (Apps left in "Testing" get refresh tokens that Google expires after a week.)
   You don't need Google's verification for personal use.
5. **Create the client:** *Clients* → **Create client** →
   *Application type*: **TVs and Limited Input devices** → name `echo-tunes` → **Create**.
   Copy the **Client ID** and **Client secret**.

### 2. Sign in

```bash
docker compose exec -it echo-tunes echo-tunes login
```

Paste the client ID and secret when asked (they're saved, so it's only asked once), then:

```text
  1. On your phone or computer, open  https://www.google.com/device
  2. Enter the code                   ABCD-EFGH
  3. Choose your YouTube Music account and allow access.

Waiting for you to approve (Ctrl-C to cancel)...
```

On the Google screens:
- Pick the account (or **brand account**) that has your YouTube Music library.
- You'll see **"Google hasn't verified this app"**. That's expected, because it's your own
  app: click **Advanced → Go to echo-tunes (unsafe)** → **Continue**.

Then restart and check:

```bash
docker compose restart echo-tunes
docker compose exec echo-tunes echo-tunes doctor
#   ✓ YouTube Music account: Signed in: your library is readable (200 liked songs)
```

> [!TIP]
> You can put the client in `.env` instead of typing it:
> `ECHO_TUNES_GOOGLE_CLIENT_ID=...` and `ECHO_TUNES_GOOGLE_CLIENT_SECRET=...`

## Browser headers (quicker, less durable)

1. On a computer, open [music.youtube.com](https://music.youtube.com) **signed in**.
2. Open developer tools (F12) → **Network** tab, and type `browse` in the filter box.
3. Click around (e.g. *Library*) until a request named `browse?...` appears; select it.
4. Copy its **request headers**:
   - Firefox: right-click the request → *Copy Value → Copy Request Headers*.
   - Chrome/Edge: *Headers* → *Request Headers* → tick **Raw** (if shown) → select all and copy.
5. On the server:
   ```bash
   docker compose exec -it echo-tunes echo-tunes login --browser
   ```
   Paste, press Enter, then **Ctrl-D**. Restart echo-tunes.

These headers contain your session cookie: treat them like a password. They stop working if
you sign out of YouTube in that browser, so a private window you then just close works well.

## YouTube Music rejects the sign-in

`echo-tunes doctor` (or the dashboard's Setup page) shows **"Signed in, but YouTube Music rejects
the account (… HTTP 400 …)"**. Nothing stops: search, radio and playback carry on without the
account; only your liked songs, playlists, mixes and "like this song" are unavailable. The check
asks Google's YouTube API with the same sign-in and says which of these it is:

| Doctor says | Fix |
| --- | --- |
| *Enable the YouTube Data API v3 …* (with a link) | Open the link (or *APIs & Services → Library → YouTube Data API v3*) → **Enable**, wait a few minutes, restart echo-tunes. The most common cause. |
| *The OAuth client doesn't match this sign-in …* | The client ID or secret changed, or the client was deleted: check `ECHO_TUNES_GOOGLE_CLIENT_ID`/`_SECRET` (or the saved client), then `echo-tunes login`. |
| *Google no longer accepts this sign-in …* | Revoked, or older than 7 days while the consent screen is in *Testing*: publish the app (step 4 above), then `echo-tunes login`. |
| *This Google account has no YouTube channel …* | At google.com/device you picked an account (often a brand account) that isn't the one with your library: `echo-tunes login` again and pick the right one. |
| *Google accepts the sign-in but YouTube Music doesn't …* | Known for brand accounts and some family-plan members: sign in with your main account, or use [browser headers](#browser-headers-quicker-less-durable). |

**"Error 400: policy_enforced"** at google.com/device (before any of this) means the account
has Google's Advanced Protection, or a Workspace admin blocks the app: use another account or
[browser headers](#browser-headers-quicker-less-durable).

The same happens when Google refuses to renew the sign-in (revoked, expired, or a changed
client): search and playback carry on, and doctor says which. After a fix, echo-tunes tries the
account again within 10 minutes (or restart it).

## Signing out

```bash
docker compose exec echo-tunes echo-tunes logout
docker compose restart echo-tunes
```

To also revoke access on Google's side: [myaccount.google.com/permissions](https://myaccount.google.com/permissions)
→ *echo-tunes* → **Delete all connections**.

## Privacy and security

- The token (`google-oauth.json` or `google-browser.json`) and the client secret are stored in
  the data folder, readable only by the echo-tunes user (mode 600). Back up and protect that
  folder like a password.
- The sign-in grants the YouTube permission that ytmusicapi needs, which covers your whole
  YouTube account (not only Music). echo-tunes only reads your library and, when you ask, likes
  a song or adds history. If you'd rather keep a distance, sign in with a
  [brand account](https://support.google.com/youtube/answer/7001996) or a second Google account
  that has your playlists.
- Nothing about your account is ever sent anywhere except to YouTube.
- The same OAuth client can also let you sign in to the dashboard with your Google account:
  see [Sign in with Google](DASHBOARD.md#sign-in-with-google). That asks only for your email
  address.
