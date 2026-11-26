"""Signed, expiring stream links.

The Echo fetches audio from ``/stream/<token>.m4a``. The token names one YouTube video and an
expiry time, signed with a key only this server knows, so the stream endpoint can't be used by
anyone else as an open proxy and old links stop working on their own.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SIG_TEXT = re.compile(r"^[A-Za-z0-9_-]{22}$")  # 16 bytes, URL-safe base64, no padding
_EXPIRY = re.compile(r"^[0-9]{1,12}$")  # ASCII only: str.isdigit() also accepts "²", "٣"
_SIG_BYTES = 16


class BadToken(Exception):
    pass


def is_video_id(value: str) -> bool:
    return bool(_VIDEO_ID.match(value))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: bytes, payload: str) -> bytes:
    return hmac.new(secret, payload.encode(), hashlib.sha256).digest()[:_SIG_BYTES]


def make(secret: bytes, video_id: str, ttl_seconds: int, now: float | None = None) -> str:
    if not is_video_id(video_id):
        raise ValueError(f"not a YouTube video ID: {video_id!r}")
    expires = int((time.time() if now is None else now) + ttl_seconds)
    payload = f"{video_id}.{expires}"
    return f"{payload}.{_b64(_sign(secret, payload))}"


def check(secret: bytes, token: str, now: float | None = None) -> str:
    """Return the video ID if the token is genuine and unexpired, else raise BadToken."""
    parts = token.split(".")
    if len(parts) != 3:
        raise BadToken("malformed")
    video_id, expires_text, sig_text = parts
    if (
        not is_video_id(video_id)
        or not _EXPIRY.match(expires_text)
        or not _SIG_TEXT.match(sig_text)  # checked before decoding: no lenient base64
    ):
        raise BadToken("malformed")
    try:
        sig = _unb64(sig_text)
    except ValueError as exc:
        raise BadToken("malformed") from exc
    if not hmac.compare_digest(sig, _sign(secret, f"{video_id}.{expires_text}")):
        raise BadToken("bad signature")
    if int(expires_text) < (time.time() if now is None else now):
        raise BadToken("expired")
    return video_id
