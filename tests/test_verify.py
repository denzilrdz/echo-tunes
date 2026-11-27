from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from echo_tunes.alexa.verify import AlexaVerifier, RequestRejected, check_cert_url

from .conftest import SKILL_ID, FakeAmazon, envelope


def make(amazon: FakeAmazon, skill_ids: list[str] | None = None) -> AlexaVerifier:
    return AlexaVerifier(skill_ids or [SKILL_ID], store=amazon.store, fetch=amazon.fetch)


def body_for(**req: object) -> bytes:
    return json.dumps(envelope({"type": "LaunchRequest", **req})).encode()


def test_accepts_a_genuine_request() -> None:
    amazon = FakeAmazon()
    body = body_for()
    assert make(amazon).verify(amazon.headers(body), body)["request"]["type"] == "LaunchRequest"


def test_rejects_tampered_body() -> None:
    amazon = FakeAmazon()
    body = body_for()
    headers = amazon.headers(body)
    with pytest.raises(RequestRejected, match="signature"):
        make(amazon).verify(headers, body.replace(b"LaunchRequest", b"IntentRequest"))


def test_rejects_other_skill() -> None:
    amazon = FakeAmazon()
    body = body_for()
    with pytest.raises(RequestRejected, match="different skill"):
        make(amazon, ["amzn1.ask.skill.someone-else"]).verify(amazon.headers(body), body)


def test_rejects_old_request() -> None:
    amazon = FakeAmazon()
    old = (datetime.now(UTC) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = body_for(timestamp=old)
    with pytest.raises(RequestRejected, match="too old"):
        make(amazon).verify(amazon.headers(body), body)


def test_rejects_wrong_certificate_name() -> None:
    amazon = FakeAmazon(san="evil.example.com")
    body = body_for()
    with pytest.raises(RequestRejected, match="not trusted"):
        make(amazon).verify(amazon.headers(body), body)


def test_rejects_expired_certificate() -> None:
    amazon = FakeAmazon(expired=True)
    body = body_for()
    with pytest.raises(RequestRejected, match="not trusted"):
        make(amazon).verify(amazon.headers(body), body)


def test_rejects_untrusted_issuer() -> None:
    amazon, stranger = FakeAmazon(), FakeAmazon()
    body = body_for()
    verifier = AlexaVerifier([SKILL_ID], store=stranger.store, fetch=amazon.fetch)
    with pytest.raises(RequestRejected, match="not trusted"):
        verifier.verify(amazon.headers(body), body)


def test_rejects_missing_headers() -> None:
    amazon = FakeAmazon()
    with pytest.raises(RequestRejected, match="missing"):
        make(amazon).verify({}, body_for())


@pytest.mark.parametrize(
    "url",
    [
        "http://s3.amazonaws.com/echo.api/echo-api-cert.pem",
        "https://notamazon.com/echo.api/echo-api-cert.pem",
        "https://s3.amazonaws.com/EcHo.aPi/echo-api-cert.pem",
        "https://s3.amazonaws.com/invalid.path/echo-api-cert.pem",
        "https://s3.amazonaws.com:563/echo.api/echo-api-cert.pem",
        "https://s3.amazonaws.com/echo.api/../evil/cert.pem",
        "https://s3.amazonaws.com/echo.api/cert.pem?x=1",
        "https://user@s3.amazonaws.com/echo.api/cert.pem",
        "https://s3.amazonaws.com/echo.api/echo-api-cert-1.pem.exe",
        "https://s3.amazonaws.com/echo.api/sub/dir.pem",
        "https://s3.amazonaws.com/echo.api/.pem",
        "https://s3.amazonaws.com/echo.api/echo-api-cert-\u0661.pem",  # Arabic-Indic digit
        "https://s3.amazonaws.com/echo.api/echo-api-cert.pem%0A",
    ],
)
def test_cert_url_rules(url: str) -> None:
    with pytest.raises(RequestRejected):
        check_cert_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://s3.amazonaws.com/echo.api/echo-api-cert.pem",
        "https://s3.amazonaws.com:443/echo.api/echo-api-cert.pem",
        "https://s3.amazonaws.com/echo.api/../echo.api/echo-api-cert.pem",
        "HTTPS://S3.AMAZONAWS.COM/echo.api/echo-api-cert.pem",
    ],
)
def test_cert_url_allowed(url: str) -> None:
    assert check_cert_url(url) == "https://s3.amazonaws.com/echo.api/echo-api-cert.pem"


@pytest.mark.parametrize("suffix", ["-12", "-12-ats", "-12345"])
def test_amazons_real_file_names_are_accepted(suffix: str) -> None:
    """0.2.2 refused every real request: Amazon's file names don't fit a fixed pattern."""
    url = f"https://s3.amazonaws.com/echo.api/echo-api-cert{suffix}.pem"
    assert check_cert_url(url) == url


def test_certificate_cache_is_bounded() -> None:
    """Many different (valid-looking) certificate URLs must not grow memory."""
    amazon = FakeAmazon()
    verifier = make(amazon)
    for i in range(50):
        body = body_for()
        verifier.verify(
            amazon.headers(body, f"https://s3.amazonaws.com/echo.api/echo-api-cert-{i}.pem"), body
        )
    assert len(verifier._certs) <= 4
    # and a repeated URL is served from the cache
    before = amazon.fetches
    body = body_for()
    verifier.verify(
        amazon.headers(body, "https://s3.amazonaws.com/echo.api/echo-api-cert-49.pem"), body
    )
    assert amazon.fetches == before


async def test_cached_certificate_requests_skip_a_backlog_of_fake_ones() -> None:
    """Audit: every new certificate URL queued a download in a 2-thread pool with no limit, so
    fake requests delayed genuine ones."""
    import asyncio
    import time

    from echo_tunes.alexa import verify as verify_mod

    amazon = FakeAmazon()
    real = "https://s3.amazonaws.com/echo.api/echo-api-cert-99.pem"

    def fetch(url: str) -> bytes:
        if url != real:
            time.sleep(0.3)  # a slow download that will fail
            raise RequestRejected("certificate download failed (403)")
        return amazon.fetch(url)

    verifier = AlexaVerifier([SKILL_ID], store=amazon.store, fetch=fetch)
    body = body_for()
    verifier.verify(amazon.headers(body, real), body)  # cached from now on
    try:
        bogus = [
            asyncio.ensure_future(
                verifier.verify_async(
                    amazon.headers(b := body_for(), f"https://s3.amazonaws.com/echo.api/x{i}.pem"),
                    b,
                )
            )
            for i in range(10)
        ]
        await asyncio.sleep(0.01)
        t0 = time.monotonic()
        body = body_for()
        assert (await verifier.verify_async(amazon.headers(body, real), body))["request"]
        assert time.monotonic() - t0 < 0.1
        results = await asyncio.gather(*bogus, return_exceptions=True)
        assert all(isinstance(e, RequestRejected) for e in results)
        refused = [e for e in results if "too many" in str(e)]
        assert len(refused) == 10 - verify_mod.MAX_PENDING_DOWNLOADS
        assert all(e.reason == "certificate" for e in refused)  # type: ignore[union-attr]
    finally:
        verifier.close()


async def test_a_cache_entry_expiring_mid_request_never_downloads_on_the_event_loop() -> None:
    """Security review: the fast path looked the certificate up, then looked it up again; if
    it expired in between, the second lookup downloaded it on the event loop."""
    import threading

    amazon = FakeAmazon()
    verifier = make(amazon)
    body = body_for()
    verifier.verify(amazon.headers(body), body)
    cache = verifier._certs
    real_get = cache.get
    lookups = [0]

    def get_once(key: str):  # type: ignore[no-untyped-def]
        lookups[0] += 1
        found = real_get(key)
        cache.pop(key)  # gone right after this lookup, as if it just expired
        return found

    cache.get = get_once  # type: ignore[method-assign]
    loop_thread = threading.get_ident()
    fetched_on: list[int] = []
    orig_fetch = amazon.fetch

    def fetch(url: str) -> bytes:
        fetched_on.append(threading.get_ident())
        return orig_fetch(url)

    verifier._fetch = fetch
    body = body_for()
    assert (await verifier.verify_async(amazon.headers(body), body))["request"]
    assert loop_thread not in fetched_on and lookups[0] == 1
    verifier.close()


def test_an_untrusted_certificate_is_not_cached() -> None:
    amazon = FakeAmazon(san="evil.example.com")
    verifier = make(amazon)
    for _ in range(3):
        body = body_for()
        with pytest.raises(RequestRejected, match="not trusted"):
            verifier.verify(amazon.headers(body), body)
    assert len(verifier._certs) == 0 and amazon.fetches == 1  # remembered as failed


async def test_requests_for_another_skill_never_download_a_certificate() -> None:
    amazon = FakeAmazon()
    verifier = make(amazon, ["amzn1.ask.skill.someone-else"])
    body = body_for()
    with pytest.raises(RequestRejected) as exc:
        await verifier.verify_async(
            amazon.headers(body, "https://s3.amazonaws.com/echo.api/new.pem"), body
        )
    assert exc.value.reason == "wrong_skill" and amazon.fetches == 0
    old = (datetime.now(UTC) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = body_for(timestamp=old)
    with pytest.raises(RequestRejected, match="too old"):
        await make(amazon).verify_async(amazon.headers(body), body)
    assert amazon.fetches == 0
    verifier.close()


def test_failed_certificate_urls_are_not_fetched_again() -> None:
    amazon = FakeAmazon()
    calls = []

    def broken(url: str) -> bytes:
        calls.append(url)
        raise RequestRejected("certificate download failed (404)")

    verifier = AlexaVerifier([SKILL_ID], store=amazon.store, fetch=broken)
    for _ in range(5):
        body = body_for()
        with pytest.raises(RequestRejected):
            verifier.verify(amazon.headers(body), body)
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("make_request", "reason"),
    [
        (lambda a: ({}, body_for()), "missing_signature"),
        (lambda a: ({**a.headers(body_for()), "Signature-256": "%%%"}, body_for()), "signature"),
        (lambda a: (a.headers(b"x" * 300_000), b"x" * 300_000), "too_large"),
        (lambda a: (a.headers(b"not json"), b"not json"), "signature"),
        (lambda a: (a.headers(b := body_for(timestamp="nope")), b), "timestamp"),
        (lambda a: (a.headers(b := body_for(timestamp=None)), b), "timestamp"),
        (
            lambda a: (
                a.headers(body_for(), cert_url="https://evil.test/echo-api-cert.pem"),
                body_for(),
            ),
            "certificate",
        ),
    ],
)
def test_every_rejection_has_its_metric_reason(make_request, reason: str) -> None:  # type: ignore[no-untyped-def]
    """Review finding: the reason label was guessed from the message text and could be wrong."""
    amazon = FakeAmazon()
    headers, body = make_request(amazon)
    with pytest.raises(RequestRejected) as exc:
        make(amazon).verify(headers, body)
    assert exc.value.reason == reason
