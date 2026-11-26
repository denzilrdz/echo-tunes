from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from echo_tunes.music import account
from echo_tunes.music.catalog import best_match

CLIENT = account.ClientSecrets("id.apps.googleusercontent.com", "secret")


class FakeGoogle:
    """Device sign-in: answers 'pending' a few times, then issues a token (or an error)."""

    def __init__(self, pending: int = 2, final_error: str | None = None) -> None:
        self.pending, self.final_error, self.polls = pending, final_error, 0

    def get_code(self) -> dict[str, Any]:
        return {
            "device_code": "dev",
            "user_code": "ABCD-EFGH",
            "interval": 5,
            "expires_in": 1800,
            "verification_url": "https://www.google.com/device",
        }

    def token_from_code(self, device_code: str) -> dict[str, Any]:
        self.polls += 1
        if self.polls <= self.pending:
            return {"error": "authorization_pending"}
        if self.final_error:
            return {"error": self.final_error}
        return {
            "access_token": "at",
            "refresh_token": "rt",
            "scope": "s",
            "token_type": "Bearer",
            "expires_in": 3599,
        }

    def refresh_token(self, refresh_token: str) -> dict[str, Any]:  # pragma: no cover
        return {"access_token": "at2", "expires_in": 3599}


def test_device_login_saves_private_token(tmp_path: Path) -> None:
    shown: list[tuple[str, str]] = []
    google = FakeGoogle()
    account.login_device(
        tmp_path,
        CLIENT,
        lambda u, c: shown.append((u, c)),
        sleep=lambda s: None,
        credentials=google,
    )
    assert shown == [("https://www.google.com/device", "ABCD-EFGH")]
    assert google.polls == 3
    token = tmp_path / account.OAUTH_FILE
    assert json.loads(token.read_text())["refresh_token"] == "rt"
    for name in (account.OAUTH_FILE, account.CLIENT_FILE):
        assert (tmp_path / name).stat().st_mode & 0o777 == 0o600
    assert account.signed_in_method(tmp_path) == "google"
    assert account.load_client(tmp_path, None, None) == CLIENT


@pytest.mark.parametrize(
    ("error", "message"), [("access_denied", "declined"), ("expired_token", "expired")]
)
def test_device_login_errors(tmp_path: Path, error: str, message: str) -> None:
    with pytest.raises(account.LoginError, match=message):
        account.login_device(
            tmp_path,
            CLIENT,
            lambda u, c: None,
            sleep=lambda s: None,
            credentials=FakeGoogle(final_error=error),
        )
    assert account.signed_in_method(tmp_path) is None


def test_browser_login_needs_cookies(tmp_path: Path) -> None:
    with pytest.raises(account.LoginError, match="cookie"):
        account.login_browser(tmp_path, "user-agent: x\n")


def test_logout_keeps_the_client_unless_asked(tmp_path: Path) -> None:
    for name in (account.OAUTH_FILE, account.CLIENT_FILE, account.BROWSER_FILE):
        (tmp_path / name).write_text("{}")
    assert account.logout(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == [account.CLIENT_FILE]
    assert not account.logout(tmp_path)
    assert account.logout(tmp_path, forget_client=True)
    assert not list(tmp_path.iterdir())


def test_settings_client_wins_over_saved_file(tmp_path: Path) -> None:
    (tmp_path / account.CLIENT_FILE).write_text(
        json.dumps({"client_id": "a", "client_secret": "b"})
    )
    assert account.load_client(tmp_path, "x", "y") == account.ClientSecrets("x", "y")
    assert account.load_client(tmp_path, None, None) == account.ClientSecrets("a", "b")


def test_anonymous_when_not_signed_in(tmp_path: Path) -> None:
    _, signed_in = account.make_client(tmp_path, "en", "", None)
    assert signed_in is False


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("road trip", "Road Trip 2026"),
        ("roadtrip", "Road Trip 2026"),
        ("work out", "Workout Mix"),
        ("chill vibes", "Chill Vibes ✨"),
        ("bollywood", "Bollywood Hits"),
        ("jazz", None),
    ],
)
def test_playlist_name_matching(said: str, expected: str | None) -> None:
    names = ["Road Trip 2026", "Workout Mix", "Chill Vibes ✨", "Bollywood Hits", "Liked Music"]
    i = best_match(said, names)
    assert (names[i] if i is not None else None) == expected
