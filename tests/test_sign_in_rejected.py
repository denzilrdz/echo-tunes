"""A YouTube Music sign-in that YouTube rejects (HTTP 400 "Request contains an invalid
argument") must not take down "play ...": search, radio and browsing carry on without the
account, personal features say why, and doctor names the cause (found testing 0.5.0-rc.2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from ytmusicapi.exceptions import YTMusicServerError

from echo_tunes.alexa.skill import SIGN_IN_REJECTED, Skill
from echo_tunes.checks import _library
from echo_tunes.music import account, catalog
from echo_tunes.music.account import ClientSecrets
from echo_tunes.music.catalog import SignInRejected, YTMusicCatalog

from .conftest import intent

REJECTED = "Server returned HTTP 400: Bad Request.\nRequest contains an invalid argument."
SONG = {"videoId": "abcdefghijk", "title": "Kesariya", "artists": [{"name": "Arijit Singh"}]}


class FakeYT:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    def _answer(self, name: str, value: Any) -> Any:
        self.calls.append(name)
        if self.error is not None:
            raise self.error
        return value

    def search(self, *a: Any, **k: Any) -> list[dict[str, Any]]:
        return self._answer("search", [SONG])  # type: ignore[no-any-return]

    def get_watch_playlist(self, *a: Any, **k: Any) -> dict[str, Any]:
        return self._answer("get_watch_playlist", {"tracks": [SONG]})  # type: ignore[no-any-return]

    def get_liked_songs(self, *a: Any, **k: Any) -> dict[str, Any]:
        return self._answer("get_liked_songs", {"tracks": [SONG]})  # type: ignore[no-any-return]


def make(error: Exception, signed_in: bool = True) -> tuple[YTMusicCatalog, FakeYT, FakeYT]:
    mine, anon = FakeYT(error), FakeYT()
    return YTMusicCatalog(mine, signed_in, anonymous=anon), mine, anon


async def test_search_and_radio_carry_on_without_a_rejected_account() -> None:
    cat, mine, anon = make(YTMusicServerError(REJECTED))
    try:
        track = await cat.search_song("kesariya")
        assert track is not None and track.title == "Kesariya"
        assert await cat.radio("abcdefghijk", 5)
        assert cat.rejection is not None and "HTTP 400" in cat.rejection
        # While rejected, the account isn't tried again for every call.
        assert mine.calls == ["search"]
        assert anon.calls == ["search", "get_watch_playlist"]
    finally:
        cat.close()


async def test_personal_features_say_the_sign_in_is_rejected() -> None:
    cat, _, anon = make(YTMusicServerError(REJECTED))
    try:
        with pytest.raises(SignInRejected):
            await cat.liked_songs()
        assert "get_liked_songs" not in anon.calls  # never someone else's (anonymous) library
    finally:
        cat.close()


async def test_the_account_is_tried_again_later(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr(catalog.time, "monotonic", lambda: clock[0])
    cat, mine, _ = make(YTMusicServerError(REJECTED))
    try:
        await cat.search_song("one")
        mine.error = None  # e.g. the API was enabled in the Cloud project
        await cat.search_song("two")
        assert mine.calls == ["search"]  # still within REJECTED_FOR
        clock[0] += catalog.REJECTED_FOR + 1
        await cat.search_song("three")
        assert mine.calls == ["search", "search"]
    finally:
        cat.close()


@pytest.mark.parametrize(
    "error",
    [
        YTMusicServerError("Server returned HTTP 500: Internal Server Error.\nBackend error."),
        ConnectionError("no route"),
    ],
)
async def test_other_errors_are_not_hidden(error: Exception) -> None:
    cat, _, anon = make(error)
    try:
        with pytest.raises(type(error)):
            await cat.search_song("kesariya")
        assert anon.calls == [] and cat.rejection is None
    finally:
        cat.close()


async def test_not_signed_in_has_nothing_to_fall_back_from() -> None:
    cat, _, anon = make(YTMusicServerError(REJECTED), signed_in=False)
    try:
        with pytest.raises(YTMusicServerError):
            await cat.search_song("kesariya")
        assert anon.calls == []
    finally:
        cat.close()


async def test_alexa_explains_a_rejected_sign_in(skill: Skill) -> None:
    async def rejected() -> Any:
        raise SignInRejected(REJECTED)

    skill.catalog.liked_songs = rejected  # type: ignore[method-assign]
    resp = await skill.handle(intent("PlayLikedIntent"))
    assert SIGN_IN_REJECTED in resp["response"]["outputSpeech"]["ssml"]


async def test_doctor_names_the_cause() -> None:
    async def rejected() -> Any:
        raise SignInRejected("Server returned HTTP 400: Bad Request.")

    async def why() -> str:
        return account.ENABLE_API

    check = await _library(rejected, why)
    assert check.status == "fail"
    assert "search, radio and playback carry on without it" in check.detail
    assert check.hint == account.ENABLE_API


# --- account.diagnose: asks Google's YouTube Data API with the same token ------------------------
CLIENT = ClientSecrets("id.apps.googleusercontent.com", "secret")
DISABLED = {
    "error": {
        "code": 403,
        "message": "YouTube Data API v3 has not been used in project 123 before or it is "
        "disabled. Enable it by visiting https://console.developers.google.com/apis/api/"
        "youtube.googleapis.com/overview?project=123 then retry.",
        "errors": [{"reason": "accessNotConfigured"}],
        "status": "PERMISSION_DENIED",
        "details": [{"reason": "SERVICE_DISABLED"}],
    }
}


def google(token: httpx.Response, channels: httpx.Response) -> httpx.AsyncClient:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if str(request.url) == account.TOKEN_URL:
            assert b"refresh_token=r3fresh" in request.content
            return token
        assert request.headers["Authorization"] == "Bearer acc3ss"
        return channels

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def signed_in(tmp_path: Path) -> Path:
    (tmp_path / account.OAUTH_FILE).write_text(json.dumps({"refresh_token": "r3fresh"}))
    return tmp_path


OK_TOKEN = httpx.Response(200, json={"access_token": "acc3ss"})


@pytest.mark.parametrize(
    ("token", "channels", "says"),
    [
        (OK_TOKEN, httpx.Response(403, json=DISABLED), "Enable the YouTube Data API v3"),
        (httpx.Response(400, json={"error": "invalid_grant"}), None, "no longer accepts"),
        (OK_TOKEN, httpx.Response(200, json={"items": []}), "no YouTube channel"),
        (OK_TOKEN, httpx.Response(200, json={"items": [{"id": "UC1"}]}), "brand accounts"),
        (OK_TOKEN, httpx.Response(401, json={}), "answered 401"),
    ],
)
async def test_diagnose(
    tmp_path: Path, token: httpx.Response, channels: httpx.Response | None, says: str
) -> None:
    http = google(token, channels or httpx.Response(500))
    try:
        why = await account.diagnose(signed_in(tmp_path), CLIENT, http)
    finally:
        await http.aclose()
    assert says in why
    assert "acc3ss" not in why and "r3fresh" not in why  # never the tokens
    if channels is not None and channels.status_code == 403:
        assert why.endswith(
            "https://console.developers.google.com/apis/api/youtube.googleapis.com/overview?project=123"
        )


async def test_diagnose_without_a_usable_sign_in(tmp_path: Path) -> None:
    assert "can't be read" in await account.diagnose(tmp_path, CLIENT)
    (tmp_path / account.BROWSER_FILE).write_text("{}")
    assert "browser headers" in await account.diagnose(tmp_path, CLIENT)
    (tmp_path / account.BROWSER_FILE).unlink()
    assert "OAuth client is missing" in await account.diagnose(signed_in(tmp_path), None)
