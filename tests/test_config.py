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
