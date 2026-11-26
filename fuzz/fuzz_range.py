"""Fuzz the Range header parser: never crash, never return bytes outside the file."""

import sys

import atheris

with atheris.instrument_imports():
    from echo_tunes.stream import StreamError, parse_range


def test_one_input(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    total = fdp.ConsumeIntInRange(1, 10**10)
    header = fdp.ConsumeUnicodeNoSurrogates(60)
    try:
        r = parse_range(header, total)
    except StreamError as exc:
        assert exc.status == 416
        return
    assert 0 <= r.start <= r.end < total, (header, total, r)


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
