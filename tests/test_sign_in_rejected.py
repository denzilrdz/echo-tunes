"""A YouTube Music sign-in that YouTube rejects (HTTP 400 "Request contains an invalid
argument") must not take down "play ...": search, radio and browsing carry on without the
account, personal features say why, and doctor names the cause (found testing 0.5.0-rc.2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import requests
import requests.adapters
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


# --- second review of #32: refusals that happen while renewing the token -------------------------
class TokenEndpoint(requests.adapters.BaseAdapter):
    """Google's token endpoint, answering every refresh with one fixed reply."""

    def __init__(self, status: int, body: dict[str, Any]) -> None:
        super().__init__()
        self.status, self.body = status, body
        self.urls: list[str] = []

    def send(self, request: Any, *args: Any, **kwargs: Any) -> requests.Response:
        self.urls.append(str(request.url))
        resp = requests.Response()
        resp.status_code = self.status
        resp._content = json.dumps(self.body).encode()
        resp.headers["Content-Type"] = "application/json"
        resp.url, resp.request = str(request.url), request
        return resp

    def close(self) -> None:
        pass


def real_signed_in_client(tmp_path: Path, endpoint: TokenEndpoint) -> Any:
    """A real ytmusicapi YTMusic whose saved token has expired, so its next call renews it."""
    from ytmusicapi import OAuthCredentials, YTMusic

    token = {
        "access_token": "old-acc3ss",
        "refresh_token": "r3fresh",
        "scope": "https://www.googleapis.com/auth/youtube",
        "token_type": "Bearer",
        "expires_at": 1,  # long expired
        "expires_in": 3599,
    }
    path = tmp_path / "oauth.json"
    path.write_text(json.dumps(token))
    session = requests.Session()
    session.mount("https://", endpoint)
    creds = OAuthCredentials("id.apps.googleusercontent.com", "secret", session=session)
    return YTMusic(str(path), oauth_credentials=creds, requests_session=session)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (
            400,
            {"error": "invalid_grant", "error_description": "Token has been expired or revoked."},
        ),
        (401, {"error": "invalid_client"}),
        (401, {"error": "unauthorized_client"}),
        (401, {"error": "something_else"}),
    ],
)
async def test_a_refused_token_renewal_falls_back_too(
    tmp_path: Path, status: int, body: dict[str, Any]
) -> None:
    """Review of #32: ytmusicapi renews the token before each call, so a revoked or expired
    sign-in (or a wrong client) failed there, with errors that never say "HTTP 400"; search
    still broke and doctor never ran its diagnosis."""
    endpoint = TokenEndpoint(status, body)
    anon = FakeYT()
    cat = YTMusicCatalog(real_signed_in_client(tmp_path, endpoint), True, anonymous=anon)
    try:
        track = await cat.search_song("kesariya")
        assert track is not None and track.title == "Kesariya"
        assert "https://oauth2.googleapis.com/token" in endpoint.urls  # the renewal was refused
        assert cat.rejection and "r3fresh" not in cat.rejection and "acc3ss" not in cat.rejection
        with pytest.raises(SignInRejected):
            await cat.liked_songs()
    finally:
        cat.close()


async def test_both_failing_is_not_a_sign_in_problem() -> None:
    cat, _, anon = make(YTMusicServerError(REJECTED))
    anon.error = YTMusicServerError("Server returned HTTP 400: Bad Request.\nBad query.")
    try:
        with pytest.raises(YTMusicServerError, match="Bad query"):
            await cat.search_song("kesariya")
        assert cat.rejection is None  # nothing switched, no "rejected the account" warning
    finally:
        cat.close()


async def test_the_retry_shares_one_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first rejected "play ..." must still answer within Alexa's ~8 s."""
    import time

    monkeypatch.setattr(catalog, "CALL_TIMEOUT", 0.3)
    monkeypatch.setattr(catalog, "RETRY_GRACE", 0.0)
    monkeypatch.setattr(catalog, "RETRY_MIN", 0.05)

    class Slow(FakeYT):
        def search(self, *a: Any, **k: Any) -> list[dict[str, Any]]:
            time.sleep(0.2)
            return super().search(*a, **k)

    mine, anon = Slow(YTMusicServerError(REJECTED)), Slow()
    cat = YTMusicCatalog(mine, True, anonymous=anon)
    try:
        t0 = time.monotonic()
        with pytest.raises(TimeoutError):  # 0.2 s used, 0.1 s left: the 0.2 s retry is cut off
            await cat.search_song("kesariya")
        assert time.monotonic() - t0 < 0.45
    finally:
        cat.close()


async def test_your_own_playlist_says_the_sign_in_is_rejected() -> None:
    class Private(FakeYT):
        def get_playlist(self, *a: Any, **k: Any) -> Any:
            return self._answer("get_playlist", None) or {}["contents"]  # as YTM: KeyError

    cat = YTMusicCatalog(FakeYT(YTMusicServerError(REJECTED)), True, anonymous=Private())
    try:
        await cat.search_song("x")  # the account is now known to be rejected
        with pytest.raises(SignInRejected):
            await cat.items_of("playlist", "PLmyownprivate")
    finally:
        cat.close()


async def test_answers_without_the_account_are_not_cached() -> None:
    class Home(FakeYT):
        def get_home(self, *a: Any, **k: Any) -> list[dict[str, Any]]:
            return self._answer("get_home", [{"title": "Quick picks", "contents": [SONG]}])  # type: ignore[no-any-return]

    mine, anon = Home(YTMusicServerError(REJECTED)), Home()
    cat = YTMusicCatalog(mine, True, anonymous=anon)
    try:
        assert await cat.home()
        assert await cat.home()
        assert anon.calls == ["get_home", "get_home"]  # asked again, not served from the cache
    finally:
        cat.close()


async def test_diagnose_a_client_mismatch(tmp_path: Path) -> None:
    http = google(httpx.Response(401, json={"error": "invalid_client"}), httpx.Response(500))
    try:
        why = await account.diagnose(signed_in(tmp_path), CLIENT, http)
    finally:
        await http.aclose()
    assert "OAuth client doesn't match" in why
