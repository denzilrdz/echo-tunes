"""Settings, read from environment variables (prefix ``ECHO_TUNES_``) or a ``.env`` file.

Nothing here knows or cares where the server runs: the only link to the outside world is
``PUBLIC_URL``, the HTTPS address that Amazon and your Echo use to reach this service.
"""

from __future__ import annotations

import os
import re
import secrets
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_TOKEN_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ECHO_TUNES_", env_file=".env", extra="ignore")

    public_url: HttpUrl = Field(
        description="Public HTTPS address of this server, e.g. https://music.example.com",
    )
    # NoDecode: read as a plain comma-separated list, not JSON
    skill_ids: Annotated[list[str], NoDecode] = Field(
        description="Your Alexa skill ID(s), amzn1.ask.skill.…; other skills are refused.",
    )
    # Where the stream key, sign-in, queues and history live. The Docker image sets /data;
    # run outside Docker, it's ./data next to where you start it.
    data_dir: Path = Path("data")
    host: str = "0.0.0.0"  # noqa: S104 - a container must listen on all interfaces
    port: int = Field(default=8080, ge=1, le=65535)
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"

    # YouTube Music
    language: str = "en"
    location: str = Field(
        default="", description="Two-letter country code for search results, e.g. US, GB, IN."
    )
    radio_length: int = Field(default=25, ge=5, le=50)
    max_queue: int = Field(default=200, ge=20, le=1000)
    ytdlp_cookies: Path | None = Field(
        default=None, description="Optional Netscape cookies.txt for yt-dlp."
    )

    # Google sign-in (optional): the OAuth client used by `echo-tunes login`. It can also be
    # typed in at login, which saves it in the data folder.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    send_history: bool = Field(
        default=False, description="Add played songs to your YouTube history (when signed in)."
    )

    # Dashboard, history and metrics: a SECOND port that must never be exposed publicly
    # (the public proxy/tunnel only forwards `port`). 0 turns the dashboard off.
    dashboard_port: int = Field(default=8081, ge=0, le=65535)
    # Loopback by default; the Docker image sets 0.0.0.0 so a port can be published (privately).
    dashboard_host: str = "127.0.0.1"
    # Extra host names the dashboard may be opened by (IP addresses, localhost and the public
    # URL's name always work). Anything else is refused, which blocks DNS-rebinding attacks.
    dashboard_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)
    dashboard_password: SecretStr | None = Field(
        default=None, description="Optional password for the dashboard and /metrics (user: admin)."
    )
    # For scripts and monitors (Uptime Kuma, Prometheus): sent as "Authorization: Bearer
    # <token>", it skips the password checks (and their queue) entirely. Long and random.
    dashboard_api_token: SecretStr | None = Field(
        default=None, description="Optional bearer token for the dashboard API and /metrics."
    )
    history_days: int = Field(default=15, ge=0, le=3650, description="0 = don't keep history.")
    # How long a phone or browser stays signed in to the dashboard; 0 = until you sign out
    # (or change the password). Fine on a private network.
    dashboard_session_days: int = Field(default=180, ge=0, le=3650)
    # Dashboard player: "Skip now" on an Echo cuts the current song's audio stream so the Echo
    # moves on. Alexa has no official way to do this; it only works if the Echo hasn't already
    # downloaded the whole song, so it's off unless you want to try it.
    experimental_skip: bool = False
    # How the dashboard looks when added to a phone's home screen (it's an installable web app).
    app_name: str = Field(default="echo-tunes", min_length=1, max_length=40)
    app_color: str = Field(default="#1f6feb", pattern=r"^#[0-9a-fA-F]{6}$")
    app_icon: Path | None = Field(
        default=None, description="Your own square PNG icon (512x512 or larger) for the app."
    )
    # Friendly Echo names: "<end of device ID>=Living room,<end>=Kitchen" (IDs are long; the
    # dashboard shows the last 12 characters to copy from).
    device_names: Annotated[dict[str, str], NoDecode] = Field(default_factory=dict)

    # Resource limits (keep memory flat no matter how long it runs)
    resolver_workers: int = Field(default=2, ge=1, le=8)
    resolver_tasks_per_worker: int = Field(default=25, ge=1, le=1000)
    stream_link_ttl_hours: int = Field(default=12, ge=1, le=48)

    @field_validator("log_level", mode="before")
    @classmethod
    def _lower_level(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("ytdlp_cookies")
    @classmethod
    def _cookies_exist(cls, v: Path | None) -> Path | None:
        if v is not None and not v.is_file():
            raise ValueError(f"cookies file {v} not found")
        return v

    @field_validator("app_icon")
    @classmethod
    def _icon_is_png(cls, v: Path | None) -> Path | None:
        if v is None:
            return v
        if not v.is_file():
            raise ValueError(f"icon file {v} not found")
        with v.open("rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                raise ValueError(f"{v} is not a PNG image")
        if v.stat().st_size > 2_000_000:
            raise ValueError(f"{v} is over 2 MB")
        return v

    @field_validator("dashboard_api_token")
    @classmethod
    def _long_token(cls, v: SecretStr | None) -> SecretStr | None:
        if v is None or not v.get_secret_value():
            return None
        token = v.get_secret_value()
        if len(token) < MIN_TOKEN_LENGTH or not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", token):
            raise ValueError(
                f"use at least {MIN_TOKEN_LENGTH} random characters (letters, digits, - _ . ~),"
                " e.g. the output of: openssl rand -hex 32"
            )
        return v

    @field_validator("skill_ids", mode="before")
    @classmethod
    def _split_ids(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("dashboard_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, v: object) -> object:
        if isinstance(v, str):
            return [h.strip().lower() for h in v.split(",") if h.strip()]
        return v

    @field_validator("dashboard_hosts")
    @classmethod
    def _bare_hosts(cls, v: list[str]) -> list[str]:
        for h in v:
            if not re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?", h):
                raise ValueError(
                    f"{h!r} is not a bare host name (no port, scheme or path), e.g. music-dash.lan"
                )
        return v

    @field_validator("device_names", mode="before")
    @classmethod
    def _parse_names(cls, v: object) -> object:
        if isinstance(v, str):
            names: dict[str, str] = {}
            for part in (p.strip() for p in v.split(",")):
                if not part:
                    continue
                key, sep, name = (s.strip() for s in part.partition("="))
                if not sep or not key or not name:
                    raise ValueError(
                        f"{part!r} isn't <end of device ID>=<name> (names can't contain commas)"
                    )
                names[key] = name
            return names
        return v

    @field_validator("dashboard_port")
    @classmethod
    def _different_port(cls, v: int, info: Any) -> int:
        if v and v == info.data.get("port"):
            raise ValueError("dashboard_port must differ from port (the public one)")
        return v

    @field_validator("skill_ids")
    @classmethod
    def _check_ids(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("set at least one skill ID")
        bad = [s for s in v if not s.startswith("amzn1.ask.skill.")]
        if bad:
            raise ValueError(
                f"not an Alexa skill ID: {bad[0]!r} (they start with amzn1.ask.skill.)"
            )
        return v

    @field_validator("public_url")
    @classmethod
    def _https_only(cls, v: HttpUrl) -> HttpUrl:
        if v.scheme != "https":
            raise ValueError(
                "Alexa only talks to HTTPS addresses; public_url must start with https://"
            )
        if (v.path or "/") != "/" or v.query or v.fragment:
            raise ValueError(
                "public_url must be just the address, e.g. https://music.example.com "
                "(no path, ? or #): echo-tunes serves /alexa and /stream at its root"
            )
        return v

    @property
    def base_url(self) -> str:
        return str(self.public_url).rstrip("/")

    @cached_property
    def stream_secret(self) -> bytes:
        """Key that signs stream links. Created on first start and kept in the data folder."""
        return self._key_file("stream.key", "links already handed to an Echo stop working")

    @cached_property
    def session_secret(self) -> bytes:
        """Key that signs dashboard sign-in cookies (with the password mixed in)."""
        return self._key_file("session.key", "everyone has to sign in to the dashboard again")

    def _key_file(self, name: str, consequence: str) -> bytes:
        path = self.data_dir / name
        if not path.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            # Written to a temporary file and renamed, so a crash can never leave a short key.
            tmp = path.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(secrets.token_bytes(32))
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(path)
        key = path.read_bytes()
        if len(key) != 32:
            raise ValueError(
                f"{path} is damaged ({len(key)} bytes, expected 32). Delete it and restart: "
                f"a new key is created ({consequence})."
            )
        return key
