"""The command line: friendly config errors, subcommand routing, logout."""

from __future__ import annotations

from pathlib import Path

import pytest

from echo_tunes import cli


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ECHO_TUNES_PUBLIC_URL", "https://music.example.com")
    monkeypatch.setenv("ECHO_TUNES_SKILL_IDS", "amzn1.ask.skill.test")
    monkeypatch.setenv("ECHO_TUNES_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


def test_bad_settings_print_a_friendly_message(
    env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ECHO_TUNES_LOG_LEVEL", "warn")
    with pytest.raises(SystemExit) as exc:
        cli._settings()
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "ECHO_TUNES_LOG_LEVEL" in out and "Traceback" not in out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0 and "echo-tunes" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "called"),
    [
        (["doctor"], ("doctor",)),
        (["login"], ("login", False)),
        (["login", "--browser"], ("login", True)),
        (["logout"], ("logout", False)),
        (["logout", "--forget-client"], ("logout", True)),
        (["serve"], ("serve",)),
        ([], ("serve",)),
    ],
)
def test_subcommands(
    argv: list[str], called: tuple[object, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[object, ...]] = []
    monkeypatch.setattr(cli, "doctor", lambda: seen.append(("doctor",)))
    monkeypatch.setattr(cli, "login", lambda b: seen.append(("login", b)))
    monkeypatch.setattr(cli, "logout", lambda f: seen.append(("logout", f)))
    monkeypatch.setattr(cli, "serve", lambda: seen.append(("serve",)))
    cli.main(argv)
    assert seen == [called]


def test_logout_when_not_signed_in(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cli.logout(False)
    assert "Not signed in" in capsys.readouterr().out


def test_logout_removes_the_token(env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from echo_tunes.music import account

    data = env / "data"
    data.mkdir()
    (data / account.OAUTH_FILE).write_text("{}")
    cli.logout(False)
    assert not (data / account.OAUTH_FILE).exists()
    assert "Signed out" in capsys.readouterr().out


def test_short_body_message_is_quieted() -> None:
    import logging

    rec = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        "",
        0,
        "ASGI callable returned without completing response.",
        None,
        None,
    )
    root = logging.getLogger()
    before = root.level
    root.setLevel(logging.INFO)
    try:
        assert cli._ShortBodyFilter().filter(rec) and rec.levelno == logging.INFO
    finally:
        root.setLevel(before)
