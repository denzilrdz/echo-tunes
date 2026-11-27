"""Fuzz the Amazon certificate URL check: only .pem files in Amazon's echo.api folder pass.

The rule (verify.CERT_FILE) is Amazon's: https, s3.amazonaws.com, port 443, a normalised path
under /echo.api/, plus a plain file name ending in .pem (Amazon's names vary, e.g.
echo-api-cert-12-ats.pem), no query, fragment or user info.
"""

import re
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
    assert clean.startswith("https://s3.amazonaws.com/echo.api/"), url
    name = clean.removeprefix("https://s3.amazonaws.com/echo.api/")
    assert re.fullmatch(r"[A-Za-z0-9._-]{1,100}\.pem", name, re.ASCII), url


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
