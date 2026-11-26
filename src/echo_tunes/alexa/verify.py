"""Checks that a request really comes from Alexa, for your skill, and is fresh.

Implements Amazon's rules for skills hosted as a web service
(https://developer.amazon.com/docs/alexa/custom-skills/host-a-custom-skill-as-a-web-service.html):

1. the certificate URL is on ``s3.amazonaws.com/echo.api/`` over HTTPS, port 443;
2. the certificate chains to a trusted root, is in date and names ``echo-api.amazon.com``;
3. the ``Signature-256`` header is a valid RSA-SHA256 signature of the exact request body;
4. the request timestamp is within 150 seconds;
5. the skill ID is one of yours.

Downloaded certificates are kept in a tiny bounded cache, and downloads have a timeout and a size
limit, so a flood of bogus requests can't grow memory or hang the server.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import posixpath
import re
import warnings
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import certifi
import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.x509.verification import PolicyBuilder, Store, VerificationError

from echo_tunes.cache import BoundedTTLCache

CERT_HOST = "s3.amazonaws.com"
CERT_PATH_PREFIX = "/echo.api/"
# Amazon's signing certificates are named echo-api-cert.pem or echo-api-cert-<n>.pem. Accepting
# only that keeps unsigned requests from making the server download arbitrary S3 objects.
# ASCII digits only and a full match (``$`` would also accept a trailing newline).
CERT_FILE = re.compile(r"/echo\.api/echo-api-cert(-[0-9]{1,4})?\.pem", re.ASCII)
FAILED_CERT_TTL = 600.0
SIGNING_NAME = "echo-api.amazon.com"
MAX_SKEW_SECONDS = 150
MAX_CERT_BYTES = 64 * 1024
MAX_BODY_BYTES = 256 * 1024


REASONS = (
    "too_large", "missing_signature", "signature", "certificate", "timestamp", "wrong_skill",
)  # fmt: skip


class RequestRejected(Exception):
    """The request is not a genuine, fresh Alexa request for this skill.

    ``reason`` is one of REASONS: a fixed metric label, set where the rejection happens.
    """

    def __init__(self, message: str, reason: str = "certificate") -> None:
        super().__init__(message)
        assert reason in REASONS, reason
        self.reason = reason


def check_cert_url(url: str) -> str:
    """Validate the SignatureCertChainUrl and return it normalised (used as the cache key)."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise RequestRejected("certificate URL is malformed") from exc
    path = posixpath.normpath(parts.path) if parts.path else ""
    if (
        parts.scheme.lower() != "https"
        or (parts.hostname or "").lower() != CERT_HOST
        or port not in (None, 443)
        or not path.startswith(CERT_PATH_PREFIX)
        or not CERT_FILE.fullmatch(path)
        or parts.query
        or parts.fragment
        or parts.username
        or parts.password
    ):
        raise RequestRejected("certificate URL is not Amazon's")
    return f"https://{CERT_HOST}{path}"


def _default_fetch(url: str) -> bytes:
    with (
        httpx.Client(timeout=5.0, follow_redirects=False) as client,
        client.stream("GET", url) as resp,
    ):
        if resp.status_code != 200:
            raise RequestRejected(f"certificate download failed ({resp.status_code})")
        data = b""
        for chunk in resp.iter_bytes():
            data += chunk
            if len(data) > MAX_CERT_BYTES:
                raise RequestRejected("certificate download too large")
        return data


def _system_store() -> Store:
    """Trusted root certificates (Mozilla's list, via certifi).

    Loaded one by one: a malformed root in the bundle is skipped instead of stopping startup.
    """
    pem = Path(certifi.where()).read_bytes()
    roots: list[x509.Certificate] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # cryptography warns about a few legacy roots
        for block in pem.split(b"-----END CERTIFICATE-----")[:-1]:
            try:
                roots.append(x509.load_pem_x509_certificate(block + b"-----END CERTIFICATE-----\n"))
            except ValueError:
                continue
    return Store(roots)


class AlexaVerifier:
    def __init__(
        self,
        skill_ids: list[str],
        *,
        store: Store | None = None,
        fetch: Callable[[str], bytes] = _default_fetch,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._skill_ids = frozenset(skill_ids)
        self._store = store or _system_store()
        self._fetch = fetch
        self._clock = clock
        self._certs: BoundedTTLCache[str, list[x509.Certificate]] = BoundedTTLCache(4, ttl=6 * 3600)
        # URLs that failed recently are refused at once instead of being fetched again.
        self._failed: BoundedTTLCache[str, str] = BoundedTTLCache(64, ttl=FAILED_CERT_TTL)
        # Its own threads: a flood of fake requests can't starve YouTube Music calls.
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alexa-verify")

    async def verify_async(self, headers: Mapping[str, str], body: bytes) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, self.verify, headers, body)

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def verify(self, headers: Mapping[str, str], body: bytes) -> dict[str, Any]:
        """Return the parsed request if genuine; raise RequestRejected otherwise.

        Blocking (may download a certificate): call it from a worker thread.
        """
        if len(body) > MAX_BODY_BYTES:
            raise RequestRejected("request too large", "too_large")
        lower = {k.lower(): v for k, v in headers.items()}
        cert_url = lower.get("signaturecertchainurl")
        signature = lower.get("signature-256")
        if not cert_url or not signature:
            raise RequestRejected("missing signature headers", "missing_signature")

        leaf = self._signing_cert(check_cert_url(cert_url))
        try:
            sig = base64.b64decode(signature, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RequestRejected("signature is not base64", "signature") from exc
        key = leaf.public_key()
        if not isinstance(key, rsa.RSAPublicKey):
            raise RequestRejected("unexpected signing key type", "signature")
        try:
            key.verify(sig, body, padding.PKCS1v15(), SHA256())
        except InvalidSignature as exc:
            raise RequestRejected("signature does not match the body", "signature") from exc

        try:
            envelope: dict[str, Any] = json.loads(body)
        except ValueError as exc:
            raise RequestRejected("body is not JSON", "signature") from exc
        self._check_timestamp(envelope)
        self._check_skill(envelope)
        return envelope

    def _signing_cert(self, url: str) -> x509.Certificate:
        chain = self._certs.get(url)
        if chain is None:
            failed = self._failed.get(url)
            if failed is not None:
                raise RequestRejected(failed)
            try:
                chain = x509.load_pem_x509_certificates(self._fetch(url))
                if not chain:
                    raise RequestRejected("certificate chain is empty")
            except (ValueError, RequestRejected, httpx.HTTPError) as exc:
                reason = (
                    str(exc) if isinstance(exc, RequestRejected) else "certificate download failed"
                )
                self._failed.set(url, reason)
                raise RequestRejected(reason) from exc
            self._certs.set(url, chain)
        # Checked on every request (not just at download) so expiry is noticed.
        verifier = (
            PolicyBuilder()
            .store(self._store)
            .time(self._clock())
            .build_server_verifier(x509.DNSName(SIGNING_NAME))
        )
        try:
            verifier.verify(chain[0], chain[1:])
        except VerificationError as exc:
            raise RequestRejected(f"certificate not trusted: {exc}") from exc
        return chain[0]

    def _check_timestamp(self, envelope: dict[str, Any]) -> None:
        raw = (envelope.get("request") or {}).get("timestamp")
        try:
            sent = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise RequestRejected("missing or bad timestamp", "timestamp") from exc
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=UTC)
        if abs((self._clock() - sent).total_seconds()) > MAX_SKEW_SECONDS:
            raise RequestRejected("request is too old", "timestamp")

    def _check_skill(self, envelope: dict[str, Any]) -> None:
        ctx_app = (((envelope.get("context") or {}).get("System") or {}).get("application")) or {}
        sess_app = ((envelope.get("session") or {}).get("application")) or {}
        app_id = ctx_app.get("applicationId") or sess_app.get("applicationId")
        if app_id not in self._skill_ids:
            raise RequestRejected("request is for a different skill", "wrong_skill")
