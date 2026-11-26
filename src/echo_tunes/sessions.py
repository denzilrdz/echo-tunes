"""Dashboard sign-in sessions: signed cookies backed by a small server-side list.

A cookie is ``<id>.<issued>.<mac>``: a random session ID, when it was issued, and an HMAC of
both. The MAC key comes from a secret in the data folder (``session.key``) mixed with a hash of
the dashboard password, so a stolen cookie says nothing about the password, and changing the
password signs every device out. The list of live session IDs (``sessions.json``, at most
``MAX_SESSIONS``) makes signing out real: a signed-out cookie stops working even if it was
copied. The issue time is checked against the *current* ``DASHBOARD_SESSION_DAYS``, so
lowering it takes effect for cookies already handed out.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

MAX_SESSIONS = 100  # signed-in browsers kept; the oldest is signed out beyond this
_COOKIE = re.compile(r"([0-9a-f]{32})\.([0-9]{1,12})\.([0-9a-f]{64})", re.ASCII)


def session_key(server_secret: bytes, password: str) -> bytes:
    """The MAC key: the server's secret, with the password mixed in (never the password)."""
    pw = hashlib.sha256(password.encode()).digest()
    return hmac.new(server_secret, b"session" + pw, hashlib.sha256).digest()


class Sessions:
    def __init__(
        self,
        key: bytes,
        days: int,
        path: Path | None = None,
        clock: Callable[[], float] = time.time,
        max_sessions: int = MAX_SESSIONS,
    ) -> None:
        self._key, self.days, self._path, self._clock = key, days, path, clock
        self._max = max_sessions
        self._lock = threading.Lock()
        self._live: dict[str, int] = {}  # session ID -> issued (unix seconds)
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text())
                self._live = {
                    str(k): int(v)
                    for k, v in dict(raw).items()
                    if isinstance(k, str) and re.fullmatch(r"[0-9a-f]{32}", k)
                }
            except (ValueError, TypeError, OSError) as exc:
                log.warning("ignoring a damaged %s (everyone signs in again): %s", path, exc)
                self._live = {}
        with self._lock:
            self._prune()

    def _mac(self, sid: str, issued: int) -> str:
        return hmac.new(self._key, f"{sid}.{issued}".encode(), hashlib.sha256).hexdigest()

    def _expired(self, issued: int, now: float) -> bool:
        return bool(self.days) and issued + self.days * 86400 < now

    def _prune(self) -> None:
        now = self._clock()
        self._live = {k: v for k, v in self._live.items() if not self._expired(v, now)}
        if len(self._live) > self._max:
            newest = sorted(self._live.items(), key=lambda kv: kv[1])[-self._max :]
            self._live = dict(newest)

    def _save(self) -> None:
        if self._path is None:
            return
        tmp = self._path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self._live, f)
        tmp.replace(self._path)

    def create(self) -> str:
        """A new signed-in session; returns the cookie value."""
        sid, issued = secrets.token_hex(16), int(self._clock())
        with self._lock:
            self._live[sid] = issued
            self._prune()
            self._save()
        return f"{sid}.{issued}.{self._mac(sid, issued)}"

    def _parse(self, value: str) -> tuple[str, int] | None:
        m = _COOKIE.fullmatch(value)
        if not m:
            return None
        sid, issued_text, mac = m.groups()
        issued = int(issued_text)
        if not hmac.compare_digest(mac, self._mac(sid, issued)):
            return None
        return sid, issued

    def valid(self, value: str) -> bool:
        parsed = self._parse(value)
        if parsed is None:
            return False
        sid, issued = parsed
        with self._lock:
            known = self._live.get(sid)
        return known == issued and not self._expired(issued, self._clock())

    def revoke(self, value: str) -> bool:
        """Sign this cookie's session out (it stops working everywhere it was copied to)."""
        parsed = self._parse(value)
        if parsed is None:
            return False
        with self._lock:
            gone = self._live.pop(parsed[0], None) is not None
            if gone:
                self._save()
        return gone

    def revoke_all(self) -> int:
        """Sign every browser out."""
        with self._lock:
            n = len(self._live)
            self._live = {}
            self._save()
        return n

    def __len__(self) -> int:
        with self._lock:
            return len(self._live)
