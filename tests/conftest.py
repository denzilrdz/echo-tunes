from __future__ import annotations

import time
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from cryptography.x509.verification import Store

from echo_tunes.alexa.skill import Skill, SkillConfig
from echo_tunes.music.catalog import Collection, NotSignedIn, Track
from echo_tunes.music.resolver import AudioSource
from echo_tunes.player.store import StateStore

SKILL_ID = "amzn1.ask.skill.00000000-test"
DEVICE = "amzn1.ask.device.TESTDEVICE"
SECRET = b"k" * 32


def song(n: int) -> Track:
    return Track(video_id=f"vid{n:08d}", title=f"Song {n}", artist=f"Artist {n}", duration=200)


class FakeCatalog:
    def __init__(self, signed_in: bool = False) -> None:
        self.searches: deque[str] = deque(maxlen=100)
        self.radios: deque[str] = deque(maxlen=100)
        self.liked: deque[str] = deque(maxlen=100)
        self.history: deque[str] = deque(maxlen=100)
        self._next = 100
        self.signed_in = signed_in
        self.failing: set[str] = set()  # method names that raise, like an unreachable YouTube

    def _maybe_fail(self, name: str) -> None:
        if name in self.failing:
            raise ConnectionError(f"{name}: YouTube Music unreachable")

    def _need(self) -> None:
        if not self.signed_in:
            raise NotSignedIn

    async def liked_songs(self) -> Collection:
        self._maybe_fail("liked_songs")
        self._need()
        return Collection("your liked songs", [song(i) for i in range(500, 520)])

    async def playlist(self, name: str) -> Collection | None:
        self._maybe_fail("playlist")
        self._need()
        if "road" not in name:
            return None
        return Collection("Road Trip", [song(i) for i in range(600, 610)])

    async def mix(self, name: str) -> Collection | None:
        self._maybe_fail("mix")
        self._need()
        return Collection("My Supermix", [song(i) for i in range(700, 750)])

    async def like(self, video_id: str) -> None:
        self._maybe_fail("like")
        self._need()
        self.liked.append(video_id)

    async def played(self, video_id: str) -> None:
        self.history.append(video_id)

    async def search_song(self, query: str) -> Track | None:
        self._maybe_fail("search_song")
        self.searches.append(query)
        return None if "nothing" in query else song(1)

    async def radio(self, video_id: str, limit: int) -> list[Track]:
        self._maybe_fail("radio")
        self.radios.append(video_id)
        start = self._next
        self._next += limit
        # YouTube's radio usually starts with the seed song itself
        return [Track(video_id, "seed", "x"), *(song(i) for i in range(start, start + limit - 1))]


class FakeResolver:
    def __init__(self) -> None:
        self.warmed: deque[str] = deque(maxlen=100)
        self.invalidated: deque[str] = deque(maxlen=100)

    async def get(self, video_id: str) -> AudioSource:
        return AudioSource(
            url=f"https://cdn.test/{video_id}",
            headers={"User-Agent": "test"},
            size=1000,
            mime="audio/mp4",
            expires=int(time.time()) + 3600,
            resolved_at=time.monotonic() - 60,
        )

    def warm(self, video_id: str) -> None:
        self.warmed.append(video_id)

    def invalidate(self, video_id: str) -> None:
        self.invalidated.append(video_id)


@pytest.fixture
def skill() -> Skill:
    cfg = SkillConfig(
        base_url="https://music.example.com",
        stream_secret=SECRET,
        stream_ttl_seconds=3600,
        radio_length=10,
        max_queue=50,
    )
    return Skill(cfg, FakeCatalog(), FakeResolver(), StateStore(":memory:"))


def envelope(
    request: dict[str, Any], *, token: str | None = None, offset: int = 0
) -> dict[str, Any]:
    request.setdefault("timestamp", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    request.setdefault("requestId", "req-1")
    ctx: dict[str, Any] = {
        "System": {
            "application": {"applicationId": SKILL_ID},
            "device": {"deviceId": DEVICE, "supportedInterfaces": {"AudioPlayer": {}}},
        }
    }
    if token:
        ctx["AudioPlayer"] = {
            "token": token,
            "offsetInMilliseconds": offset,
            "playerActivity": "PLAYING",
        }
    return {"version": "1.0", "context": ctx, "request": request}


def intent(name: str, query: str | None = None) -> dict[str, Any]:
    slots = {"query": {"name": "query", "value": query}} if query is not None else {}
    return envelope({"type": "IntentRequest", "intent": {"name": name, "slots": slots}})


def event(kind: str, token: str, **extra: Any) -> dict[str, Any]:
    return envelope({"type": kind, "token": token, **extra})


def directives(resp: dict[str, Any]) -> list[dict[str, Any]]:
    return resp["response"].get("directives", [])  # type: ignore[no-any-return]


# --- a fake Amazon certificate authority, for signature tests --------------------------------
class FakeAmazon:
    """Issues a signing certificate like Amazon's (SAN echo-api.amazon.com) from a test CA."""

    def __init__(self, *, san: str = "echo-api.amazon.com", expired: bool = False) -> None:
        now = datetime.now(UTC)
        self.ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Root CA")])
        self.ca = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(self.ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(False, False, False, False, False, True, True, False, False),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(self.ca_key.public_key()), critical=False
            )
            .sign(self.ca_key, hashes.SHA256())
        )
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        start, end = (
            (now - timedelta(days=10), now - timedelta(days=1))
            if expired
            else (now - timedelta(days=1), now + timedelta(days=10))
        )
        self.leaf = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, san)]))
            .issuer_name(ca_name)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(start)
            .not_valid_after(end)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
            .add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(self.ca_key.public_key()),
                critical=False,
            )
            .sign(self.ca_key, hashes.SHA256())
        )
        self.fetches = 0

    @property
    def store(self) -> Store:
        return Store([self.ca])

    def fetch(self, url: str) -> bytes:
        self.fetches += 1
        return self.leaf.public_bytes(serialization.Encoding.PEM)

    def headers(
        self, body: bytes, cert_url: str = "https://s3.amazonaws.com/echo.api/echo-api-cert-99.pem"
    ) -> dict[str, str]:
        import base64

        sig = self.key.sign(body, padding.PKCS1v15(), hashes.SHA256())
        return {"SignatureCertChainUrl": cert_url, "Signature-256": base64.b64encode(sig).decode()}
