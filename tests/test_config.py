from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from echo_tunes.config import Settings

ID1, ID2 = "amzn1.ask.skill.aaa", "amzn1.ask.skill.bbb"


def make(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **env: str) -> Settings:
    monkeypatch.chdir(tmp_path)  # no stray .env
    base = {"PUBLIC_URL": "https://music.example.com/", "SKILL_IDS": ID1, "DATA_DIR": str(tmp_path)}
    for k, v in {**base, **env}.items():
        monkeypatch.setenv(f"ECHO_TUNES_{k}", v)
    return Settings()  # type: ignore[call-arg]


def test_location_and_language_are_normalised(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Audit: a lower-case or unknown location/language crashed serve and doctor with a
    ytmusicapi traceback instead of a configuration message."""
    s = make(monkeypatch, tmp_path, LOCATION=" in ", LANGUAGE="DE")
    assert (s.location, s.language) == ("IN", "de")
    s = make(monkeypatch, tmp_path, LOCATION="", LANGUAGE="zh-cn")
    assert (s.location, s.language) == ("", "zh_CN")
    with pytest.raises(ValidationError, match="two-letter"):
        make(monkeypatch, tmp_path, LOCATION="XX")
    with pytest.raises(ValidationError, match="try 'en'"):
        make(monkeypatch, tmp_path, LANGUAGE="en-US")
    with pytest.raises(ValidationError, match="isn't a language"):
        make(monkeypatch, tmp_path, LANGUAGE="klingon")


def test_cli_explains_a_bad_location(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from echo_tunes import cli

    monkeypatch.chdir(tmp_path)
    for k, v in {"PUBLIC_URL": "https://music.example.com", "SKILL_IDS": ID1,
                 "DATA_DIR": str(tmp_path), "LOCATION": "usa"}.items():  # fmt: skip
        monkeypatch.setenv(f"ECHO_TUNES_{k}", v)
    with pytest.raises(SystemExit) as exit_:
        cli._settings()
    assert exit_.value.code == 2
    assert "ECHO_TUNES_LOCATION" in capsys.readouterr().out


def test_every_setting_is_documented() -> None:
    """Audit: .env.example was missing seven settings."""
    root = Path(__file__).parent.parent
    for doc in ("README.md", ".env.example"):
        path = root / doc
        if not path.exists():  # e.g. an sdist without .env.example
            continue
        text = path.read_text()
        missing = [n for n in Settings.model_fields if f"ECHO_TUNES_{n.upper()}" not in text]
        assert not missing, f"{doc} lacks {missing}"


def test_reads_comma_separated_skill_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    s = make(monkeypatch, tmp_path, SKILL_IDS=f"{ID1}, {ID2}")
    assert s.skill_ids == [ID1, ID2]
    assert s.base_url == "https://music.example.com"


@pytest.mark.parametrize(
    "env",
    [
        {"PUBLIC_URL": "http://music.example.com"},
        {"SKILL_IDS": "not-a-skill"},
        {"SKILL_IDS": " , "},
        {"PUBLIC_URL": "https://music.example.com/echo"},
        {"PUBLIC_URL": "https://music.example.com/?x=1"},
        {"LOG_LEVEL": "warn"},
        {"LOG_LEVEL": "trace"},
        {"DASHBOARD_HOSTS": "music-dash.lan:8081"},
        {"DEVICE_NAMES": "abc=Living room, kitchen"},
        {"YTDLP_COOKIES": "/nonexistent/cookies.txt"},
        {"PORT": "0"},
        {"APP_COLOR": "blue"},
        {"APP_ICON": "/nonexistent/icon.png"},
        {"APP_NAME": ""},
    ],
)
def test_rejects_bad_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, env: dict[str, str]
) -> None:
    with pytest.raises(ValidationError):
        make(monkeypatch, tmp_path, **env)


def test_stream_key_is_created_once_and_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = make(monkeypatch, tmp_path).stream_secret
    assert len(key) == 32
    assert (tmp_path / "stream.key").stat().st_mode & 0o777 == 0o600
    assert make(monkeypatch, tmp_path).stream_secret == key


def test_damaged_stream_key_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "stream.key").write_bytes(b"")
    with pytest.raises(ValueError, match="damaged"):
        _ = make(monkeypatch, tmp_path).stream_secret


def test_log_level_is_case_insensitive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert make(monkeypatch, tmp_path, LOG_LEVEL="DEBUG").log_level == "debug"


def test_data_dir_defaults_to_a_local_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ECHO_TUNES_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    for k, v in {"PUBLIC_URL": "https://music.example.com", "SKILL_IDS": ID1}.items():
        monkeypatch.setenv(f"ECHO_TUNES_{k}", v)
    assert Settings().data_dir == Path("data")  # type: ignore[call-arg]


def test_app_icon_must_be_a_png(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "icon.png"
    fake.write_text("<svg/>")
    with pytest.raises(ValidationError, match="not a PNG"):
        make(monkeypatch, tmp_path, APP_ICON=str(fake))


def test_google_emails_for_the_dashboard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    s = make(
        monkeypatch,
        tmp_path,
        DASHBOARD_PASSWORD="pw",
        DASHBOARD_GOOGLE_EMAILS=" Me@Gmail.com , partner@example.org,",
    )
    assert s.dashboard_google_emails == ["me@gmail.com", "partner@example.org"]
    for bad in ("not-an-email", "a@b@c.com", "me@localhost"):
        with pytest.raises(ValidationError):
            make(monkeypatch, tmp_path, DASHBOARD_PASSWORD="pw", DASHBOARD_GOOGLE_EMAILS=bad)
    monkeypatch.delenv("ECHO_TUNES_DASHBOARD_PASSWORD")
    with pytest.raises(ValidationError, match="password"):  # Google sign-in adds to it
        make(monkeypatch, tmp_path, DASHBOARD_GOOGLE_EMAILS="me@gmail.com")
