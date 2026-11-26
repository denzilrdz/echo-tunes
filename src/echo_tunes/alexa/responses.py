"""Builders for Alexa response JSON (speech and AudioPlayer directives)."""

from __future__ import annotations

from typing import Any

from echo_tunes.music.catalog import Track

Response = dict[str, Any]


def _ssml_escape(text: str) -> str:
    return text.replace("&", " and ").replace("<", " ").replace(">", " ").replace('"', "").strip()


def build(
    speech: str | None = None,
    *,
    reprompt: str | None = None,
    directives: list[dict[str, Any]] | None = None,
    end_session: bool | None = True,
) -> Response:
    body: dict[str, Any] = {}
    if speech:
        body["outputSpeech"] = {"type": "SSML", "ssml": f"<speak>{_ssml_escape(speech)}</speak>"}
    if reprompt:
        body["reprompt"] = {
            "outputSpeech": {"type": "SSML", "ssml": f"<speak>{_ssml_escape(reprompt)}</speak>"}
        }
    if directives:
        body["directives"] = directives
    if end_session is not None:
        body["shouldEndSession"] = end_session
    return {"version": "1.0", "response": body}


def empty() -> Response:
    """For AudioPlayer/PlaybackController events, which must not speak."""
    return {"version": "1.0", "response": {}}


def only(*directives: dict[str, Any]) -> Response:
    """Directives with no speech, for playback events and hardware buttons."""
    return {"version": "1.0", "response": {"directives": list(directives)}}


def play(
    track: Track,
    *,
    url: str,
    token: str,
    behavior: str = "REPLACE_ALL",
    offset_ms: int = 0,
    expected_previous: str | None = None,
) -> dict[str, Any]:
    stream: dict[str, Any] = {"url": url, "token": token, "offsetInMilliseconds": offset_ms}
    if behavior == "ENQUEUE" and expected_previous:
        stream["expectedPreviousToken"] = expected_previous
    return {
        "type": "AudioPlayer.Play",
        "playBehavior": behavior,
        "audioItem": {
            "stream": stream,
            "metadata": {"title": track.title, "subtitle": track.artist},
        },
    }


def stop() -> dict[str, Any]:
    return {"type": "AudioPlayer.Stop"}


def clear_enqueued() -> dict[str, Any]:
    return {"type": "AudioPlayer.ClearQueue", "clearBehavior": "CLEAR_ENQUEUED"}
