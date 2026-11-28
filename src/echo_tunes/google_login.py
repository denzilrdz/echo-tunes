"""Signing in to the dashboard with a Google account, as well as with the password.

It uses Google's sign-in for TVs and limited-input devices, the same kind of OAuth client as
``echo-tunes login``: the dashboard shows a short code, you approve it at google.com/device on
your phone, and the server asks Google who approved it. There is no redirect back to the
dashboard, so it works on a LAN address over plain HTTP (Google only redirects to HTTPS
addresses with a public domain name, or localhost).

Only the ``openid email`` scopes are asked for. The identity token comes straight from
Google's token endpoint over TLS, so its signature needn't be checked again (OpenID Connect
Core 3.1.3.7); its issuer, audience, expiry and verified email are. Only addresses in
``ECHO_TUNES_DASHBOARD_GOOGLE_EMAILS`` get in. Google's tokens are dropped at once and never
revoked: revoking would also end the YouTube Music sign-in made with the same client.

Pending sign-ins are capped (``MAX_PENDING``) and expire after ``FLOW_SECONDS``. A sign-in
whose page went quiet is kept (a phone suspends a page in the background while you approve the
code in another tab); only when the cap is reached may a new one push out a sign-in nobody has
checked on for ``STALE_SECONDS``, never one in use, else the new one is refused. Starts are
limited to ``MAX_STARTS`` a minute in total, so unauthenticated callers can't make the server
call Google without limit.

Like every TV-style sign-in, approving a code someone else started signs *them* in; the page
and docs say to only enter a code you started yourself.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import secrets
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 (a URL, not a password)
SCOPE = "openid email"
ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
MAX_PENDING = 8  # sign-ins waiting for approval at once
FLOW_SECONDS = 600  # a code is good for this long here (Google allows longer)
# When the table is full, a sign-in nobody has checked on for this long may be pushed out.
# Long enough to approve a code in another tab while the phone suspends this page.
STALE_SECONDS = 120.0
MAX_STARTS = 10  # sign-ins started per minute, in total
CLOCK_SKEW = 300  # seconds of leeway on the token's expiry


class GoogleLoginError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(slots=True)
class _Flow:
    device_code: str
    interval: float
    expires: float  # time.monotonic()
    next_poll: float
    seen: float  # when the browser last checked on it
    busy: bool = False


class GoogleLogin:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        emails: frozenset[str],
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._id, self._secret = client_id, client_secret
        self._emails = frozenset(e.lower() for e in emails)
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0))
        self._flows: dict[str, _Flow] = {}
        self._starts: deque[float] = deque(maxlen=MAX_STARTS)

    async def start(self) -> dict[str, Any]:
        """Ask Google for a code to show. ``flow`` is the secret the browser polls with."""
        self._prune()
        now = time.monotonic()
        if len(self._starts) == MAX_STARTS and now - self._starts[0] < 60:
            raise GoogleLoginError(429, "Too many Google sign-ins started; try again in a minute.")
        if not self._make_room(now):
            raise GoogleLoginError(429, "Too many Google sign-ins waiting; try again shortly.")
        self._starts.append(now)
        data = await self._post(DEVICE_CODE_URL, {"client_id": self._id, "scope": SCOPE})
        code, device_code = data.get("user_code"), data.get("device_code")
        if not isinstance(code, str) or not isinstance(device_code, str):
            log.warning("Google refused a sign-in code: %s", _error(data))
            raise GoogleLoginError(502, "Google refused the sign-in. Check the OAuth client.")
        url = data.get("verification_url") or data.get("verification_uri")
        if not isinstance(url, str) or not url.startswith("https://"):
            url = "https://www.google.com/device"
        interval = min(max(_number(data.get("interval"), 5.0), 1.0), 30.0)
        lifetime = min(max(_number(data.get("expires_in"), FLOW_SECONDS), 30.0), FLOW_SECONDS)
        now = time.monotonic()
        self._prune()
        if not self._make_room(now):  # others started while Google answered
            raise GoogleLoginError(429, "Too many Google sign-ins waiting; try again shortly.")
        flow = secrets.token_urlsafe(32)
        self._flows[flow] = _Flow(device_code, interval, now + lifetime, now + interval, now)
        return {
            "flow": flow,
            "url": url[:200],
            "code": code[:40],
            "interval": interval,
            "expires_in": int(lifetime),
        }

    async def poll(self, flow_id: str) -> str | None:
        """The allowed email once the code is approved; None while waiting."""
        self._prune()
        flow = self._flows.get(flow_id)
        if flow is None:
            raise GoogleLoginError(410, "This sign-in code expired. Start again.")
        now = time.monotonic()
        flow.seen = now
        if flow.busy or now < flow.next_poll:
            return None  # Google asks for at most one check per interval
        flow.busy = True
        try:
            data = await self._post(
                TOKEN_URL,
                {
                    "client_id": self._id,
                    "client_secret": self._secret,
                    "device_code": flow.device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
        finally:
            flow.busy = False
            flow.next_poll = time.monotonic() + flow.interval
        error = data.get("error")
        if error == "authorization_pending":
            return None
        if error == "slow_down":
            flow.interval = min(flow.interval + 5, 30.0)
            return None
        self._flows.pop(flow_id, None)  # finished, one way or another
        if error == "access_denied":
            raise GoogleLoginError(403, "Sign-in was declined on Google's page.")
        if error == "expired_token":
            raise GoogleLoginError(410, "This sign-in code expired. Start again.")
        if error:
            log.warning("Google sign-in failed: %s", _error(data))
            raise GoogleLoginError(502, "Google didn't finish the sign-in. Try again.")
        email = self._check(data.get("id_token"))
        if email not in self._emails:
            log.warning("a Google account that isn't allowed tried to sign in to the dashboard")
            raise GoogleLoginError(
                403,
                "This Google account isn't allowed. Add it to ECHO_TUNES_DASHBOARD_GOOGLE_EMAILS.",
            )
        log.info("a Google account signed in to the dashboard")
        return email

    def _check(self, id_token: Any) -> str:
        """The verified, lower-case email in Google's identity token."""
        claims = _claims(id_token)
        try:
            ok = (
                claims["iss"] in ISSUERS
                and claims["aud"] == self._id
                and float(claims["exp"]) > time.time() - CLOCK_SKEW
                and claims.get("email_verified") in (True, "true")
                and isinstance(claims.get("email"), str)
            )
        except (KeyError, TypeError, ValueError):
            ok = False
        if not ok:
            raise GoogleLoginError(502, "Google's answer couldn't be checked. Try again.")
        return str(claims["email"]).strip().lower()

    async def _post(self, url: str, form: dict[str, str]) -> dict[str, Any]:
        try:
            resp = await self._http.post(url, data=form, headers={"Accept": "application/json"})
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("couldn't reach Google for sign-in: %s", type(exc).__name__)
            raise GoogleLoginError(502, "Couldn't reach Google. Try again.") from exc
        if not isinstance(data, dict):
            raise GoogleLoginError(502, "Google's answer couldn't be read. Try again.")
        return data

    def _make_room(self, now: float) -> bool:
        """Free a place if the table is full, pushing out only a sign-in nobody checks on."""
        if len(self._flows) < MAX_PENDING:
            return True
        stalest = min(self._flows, key=lambda k: self._flows[k].seen)
        if now - self._flows[stalest].seen < STALE_SECONDS:
            return False  # every one is in use
        del self._flows[stalest]
        return True

    def _prune(self) -> None:
        now = time.monotonic()
        for key in [k for k, f in self._flows.items() if f.expires <= now]:
            del self._flows[key]

    @property
    def emails(self) -> frozenset[str]:
        """The accounts allowed in (sessions check them again on every request)."""
        return self._emails

    def __len__(self) -> int:
        return len(self._flows)

    async def aclose(self) -> None:
        await self._http.aclose()


def _claims(id_token: Any) -> dict[str, Any]:
    """The payload of a JWT, without checking its signature (see the module docstring)."""
    if not isinstance(id_token, str) or id_token.count(".") != 2 or len(id_token) > 8192:
        raise GoogleLoginError(502, "Google sent no identity. Try again.")
    payload = id_token.split(".")[1]
    try:
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        claims = json.loads(raw)
    except (binascii.Error, ValueError) as exc:
        raise GoogleLoginError(502, "Google's identity couldn't be read. Try again.") from exc
    if not isinstance(claims, dict):
        raise GoogleLoginError(502, "Google's identity couldn't be read. Try again.")
    return claims


def _number(value: Any, default: float) -> float:
    """A positive number from Google's answer, else ``default``."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return n if n > 0 and n == n else default  # n == n: not NaN


def _error(data: dict[str, Any]) -> str:
    """Google's error code only (never tokens), short."""
    return str(data.get("error") or "no code")[:60]
