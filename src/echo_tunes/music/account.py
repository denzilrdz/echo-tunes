"""Signing in to YouTube Music, so radio, playlists, likes and mixes are your own.

Two ways, both run from the command line on the server (never through a web page, because the
server is reachable from the internet):

* ``echo-tunes login``: Google's TV-style sign-in. You open google.com/device on your phone and
  type a short code. Needs a free OAuth client of type "TVs and Limited Input devices" from
  Google Cloud (see docs/GOOGLE_SIGN_IN.md). The token refreshes itself.
* ``echo-tunes login --browser``: paste the request headers of a signed-in music.youtube.com
  tab. Quicker, but stops working when that browser session ends.

Only YouTube Music browsing (search, radio, library, likes) uses the account. Audio links are
always fetched anonymously, so your account is never used for downloading.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OAUTH_FILE = "google-oauth.json"
CLIENT_FILE = "google-client.json"
BROWSER_FILE = "google-browser.json"


class LoginError(Exception):
    pass


def timeout_session(seconds: float = 8.0) -> Any:
    """A requests session whose calls give up after `seconds` (ytmusicapi sets none)."""
    import requests

    class TimeoutSession(requests.Session):
        def request(self, *args: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("timeout", seconds)
            return super().request(*args, **kwargs)

    return TimeoutSession()


@dataclass(frozen=True, slots=True)
class ClientSecrets:
    client_id: str
    client_secret: str


def _write_private(path: Path, data: str) -> None:
    """Write a file only the owner can read, without a window where it's world-readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
    tmp.replace(path)


def load_client(
    data_dir: Path, client_id: str | None, client_secret: str | None
) -> ClientSecrets | None:
    """Client secrets from settings, else from the file saved at login."""
    if client_id and client_secret:
        return ClientSecrets(client_id, client_secret)
    path = data_dir / CLIENT_FILE
    if path.exists():
        d = json.loads(path.read_text())
        return ClientSecrets(d["client_id"], d["client_secret"])
    return None


def signed_in_method(data_dir: Path) -> str | None:
    if (data_dir / OAUTH_FILE).exists():
        return "google"
    if (data_dir / BROWSER_FILE).exists():
        return "browser"
    return None


def make_client(
    data_dir: Path, language: str, location: str, client: ClientSecrets | None
) -> tuple[Any, bool]:
    """Return ``(YTMusic, signed_in)``. Falls back to anonymous if sign-in is incomplete."""
    from ytmusicapi import OAuthCredentials, YTMusic

    oauth = data_dir / OAUTH_FILE
    browser = data_dir / BROWSER_FILE
    if oauth.exists() and client is not None:
        creds = OAuthCredentials(client.client_id, client.client_secret)
        return YTMusic(
            str(oauth),
            language=language,
            location=location,
            oauth_credentials=creds,
            requests_session=timeout_session(),
        ), True
    if browser.exists():
        return YTMusic(
            str(browser), language=language, location=location, requests_session=timeout_session()
        ), True
    return YTMusic(language=language, location=location, requests_session=timeout_session()), False


def anonymous_client(language: str, location: str) -> Any:
    """A YTMusic without any account: search, radio and browsing keep working with it when
    YouTube Music rejects the signed-in one (see catalog.YTMusicCatalog)."""
    from ytmusicapi import YTMusic

    return YTMusic(language=language, location=location, requests_session=timeout_session())


# --- why YouTube Music rejects a sign-in (for doctor) ---------------------------------------------
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 (a URL)
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels?part=id&mine=true"
_ENABLE_URL = re.compile(
    r"https://console\.(?:developers|cloud)\.google\.com/apis/api/youtube\.googleapis\.com/"
    r"overview\?project=\d+"
)
ENABLE_API = (
    "Enable the YouTube Data API v3 in the Google Cloud project of your OAuth client (APIs &"
    " Services, Library, YouTube Data API v3, Enable), wait a few minutes, then restart echo-tunes"
)


async def diagnose(data_dir: Path, client: ClientSecrets | None, http: Any = None) -> str:
    """Why YouTube Music may reject the saved sign-in, asked of Google's YouTube Data API with
    the same token. Never returns or logs the token itself."""
    import httpx

    if signed_in_method(data_dir) == "browser":
        return (
            "The pasted browser headers were rejected; copy fresh ones (echo-tunes login --browser)"
        )
    try:
        refresh = json.loads((data_dir / OAUTH_FILE).read_text())["refresh_token"]
    except (OSError, ValueError, KeyError, TypeError):
        return "The saved sign-in can't be read: sign in again (echo-tunes login)"
    if client is None:
        return "The OAuth client is missing: sign in again (echo-tunes login)"
    own = http is None
    http = http or httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
    try:
        token = await http.post(
            TOKEN_URL,
            data={
                "client_id": client.client_id,
                "client_secret": client.client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
        if token.status_code != 200:
            return (
                "Google no longer accepts this sign-in (revoked, or older than 7 days while the"
                " app is in Testing mode): publish the app, then echo-tunes login"
            )
        access = token.json().get("access_token", "")
        resp = await http.get(CHANNELS_URL, headers={"Authorization": f"Bearer {access}"})
    except (httpx.HTTPError, ValueError) as exc:
        return f"Couldn't ask Google about the sign-in ({type(exc).__name__}); try again"
    finally:
        if own:
            await http.aclose()
    text = resp.text
    if resp.status_code == 403 and ("SERVICE_DISABLED" in text or "accessNotConfigured" in text):
        link = _ENABLE_URL.search(text)
        return ENABLE_API + (f": {link.group(0)}" if link else "")
    if resp.status_code != 200:
        return f"Google's YouTube API answered {resp.status_code}: sign in again (echo-tunes login)"
    if not (resp.json().get("items") or []):
        return (
            "This Google account has no YouTube channel (often a brand account or a new account):"
            " sign in again and pick the account that has your YouTube Music library"
        )
    return (
        "Google accepts the sign-in but YouTube Music doesn't. Known for brand accounts and some"
        " family-plan members: sign in with your main account, or use echo-tunes login --browser"
    )


# --- login flows (used by the CLI) ---------------------------------------------------------------
def login_device(
    data_dir: Path,
    client: ClientSecrets,
    show: Callable[[str, str], None],
    sleep: Callable[[float], None] = time.sleep,
    credentials: Any = None,
) -> None:
    """Google device sign-in: show a code, wait for the user to approve it, save the token."""
    from ytmusicapi import OAuthCredentials
    from ytmusicapi.auth.oauth import RefreshingToken

    creds = credentials or OAuthCredentials(client.client_id, client.client_secret)
    try:
        code = creds.get_code()
    except Exception as exc:
        raise LoginError(f"Google refused the client ID/secret: {exc}") from exc
    if "user_code" not in code:
        raise LoginError(
            f"Google refused the client ID/secret: {code.get('error_description') or code}"
        )
    show(code["verification_url"], code["user_code"])

    interval = float(code.get("interval", 5))
    deadline = time.monotonic() + float(code.get("expires_in", 1800))
    while True:
        sleep(interval)
        if time.monotonic() > deadline:
            raise LoginError("The code expired before it was approved. Run login again.")
        token = creds.token_from_code(code["device_code"])
        error = str(token.get("error") or "")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error:
            raise LoginError(
                {
                    "access_denied": "Sign-in was declined.",
                    "expired_token": "The code expired.",
                }.get(error, f"Google said: {token.get('error_description') or error}")
            )
        break

    ref = RefreshingToken(
        credentials=creds,
        access_token=token["access_token"],
        refresh_token=token["refresh_token"],
        scope=token["scope"],
        token_type=token["token_type"],
        expires_in=token["expires_in"],
    )
    ref.update(token)
    _write_private(data_dir / OAUTH_FILE, json.dumps(ref.as_dict(), indent=1))
    _write_private(
        data_dir / CLIENT_FILE,
        json.dumps({"client_id": client.client_id, "client_secret": client.client_secret}),
    )
    (data_dir / BROWSER_FILE).unlink(missing_ok=True)


def login_browser(data_dir: Path, headers_raw: str) -> None:
    """Save pasted request headers from a signed-in music.youtube.com tab."""
    from ytmusicapi import setup

    if "cookie" not in headers_raw.lower():
        raise LoginError("Those headers have no cookie line. Copy them from a signed-in tab.")
    try:
        saved = setup(filepath=None, headers_raw=headers_raw)
    except Exception as exc:
        raise LoginError(f"Couldn't read those headers: {exc}") from exc
    _write_private(data_dir / BROWSER_FILE, saved)
    (data_dir / OAUTH_FILE).unlink(missing_ok=True)


def logout(data_dir: Path, *, forget_client: bool = False) -> bool:
    """Remove the sign-in. The OAuth client is kept (so the next login doesn't ask for it)
    unless `forget_client` is set."""
    removed = False
    names = (OAUTH_FILE, BROWSER_FILE, CLIENT_FILE) if forget_client else (OAUTH_FILE, BROWSER_FILE)
    for name in names:
        path = data_dir / name
        if path.exists():
            path.unlink()
            removed = True
    return removed
