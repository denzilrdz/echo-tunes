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
            str(oauth), language=language, location=location, oauth_credentials=creds
        ), True
    if browser.exists():
        return YTMusic(str(browser), language=language, location=location), True
    return YTMusic(language=language, location=location), False


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


def logout(data_dir: Path) -> bool:
    removed = False
    for name in (OAUTH_FILE, CLIENT_FILE, BROWSER_FILE):
        path = data_dir / name
        if path.exists():
            path.unlink()
            removed = True
    return removed
