"""Fuzz Alexa's playback tokens and stored player state: never crash, stay in bounds."""

import contextlib
import json
import sys

import atheris

with atheris.instrument_imports():
    from echo_tunes.music.catalog import Track
    from echo_tunes.player.state import PlayerState


def test_one_input(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    state = PlayerState()
    state.replace(
        [Track(f"vid{i:08d}", f"t{i}", "a") for i in range(fdp.ConsumeIntInRange(0, 30))], 50
    )
    idx = state.index_from_token(fdp.ConsumeUnicodeNoSurrogates(80))
    assert idx is None or 0 <= idx < len(state.tracks)
    # Stored state comes back from SQLite; damaged JSON must fail cleanly, not crash oddly.
    raw = fdp.ConsumeUnicodeNoSurrogates(300)
    with contextlib.suppress(ValueError, TypeError, KeyError, AttributeError):
        PlayerState.from_dict(json.loads(raw))


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
