"""Fuzz the stream-link check: random links must be refused cleanly, never accepted."""

import sys

import atheris

with atheris.instrument_imports():
    from echo_tunes import tokens

SECRET = b"k" * 32
GOOD = tokens.make(SECRET, "dQw4w9WgXcQ", 3600, now=0)


def test_one_input(data: bytes) -> None:
    text = atheris.FuzzedDataProvider(data).ConsumeUnicodeNoSurrogates(200)
    try:
        video = tokens.check(SECRET, text, now=0)
    except tokens.BadToken:
        return
    # Anything accepted must name the same song and expiry as a link we actually issued.
    if video != "dQw4w9WgXcQ" or text.split(".")[:2] != GOOD.split(".")[:2]:
        raise AssertionError(f"forged link accepted: {text!r}")


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
