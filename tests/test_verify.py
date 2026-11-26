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
        "https://s3.amazonaws.com/echo.api/anything-else.pem",
        "https://s3.amazonaws.com/echo.api/echo-api-cert-1.pem.exe",
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
