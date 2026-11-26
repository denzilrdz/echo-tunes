"""Fuzz the Amazon certificate URL check: only Amazon's certificate files may pass."""

import sys

import atheris

with atheris.instrument_imports():
    from echo_tunes.alexa.verify import RequestRejected, check_cert_url


def test_one_input(data: bytes) -> None:
    url = atheris.FuzzedDataProvider(data).ConsumeUnicodeNoSurrogates(200)
    try:
        clean = check_cert_url(url)
    except RequestRejected:
        return
    assert clean.startswith("https://s3.amazonaws.com/echo.api/echo-api-cert"), url
    assert clean.endswith(".pem") and "?" not in clean and "#" not in clean, url


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
