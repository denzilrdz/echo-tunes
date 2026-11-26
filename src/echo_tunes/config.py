"""Settings, read from environment variables (prefix ``ECHO_TUNES_``) or a ``.env`` file.

Nothing here knows or cares where the server runs: the only link to the outside world is
``PUBLIC_URL``, the HTTPS address that Amazon and your Echo use to reach this service.
"""

from __future__ import annotations

import secrets
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ECHO_TUNES_", env_file=".env", extra="ignore")

    public_url: HttpUrl = Field(
        description="Public HTTPS address of this server, e.g. https://music.example.com",
    )
    # NoDecode: read as a plain comma-separated list, not JSON
    skill_ids: Annotated[list[str], NoDecode] = Field(
        description="Your Alexa skill ID(s), amzn1.ask.skill.…; other skills are refused.",
    )
    data_dir: Path = Path("/data")
    host: str = "0.0.0.0"  # noqa: S104 - a container must listen on all interfaces
    port: int = 8080
    log_level: str = "info"

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
    history_days: int = Field(default=15, ge=0, le=3650, description="0 = don't keep history.")
    # Friendly Echo names: "<end of device ID>=Living room,<end>=Kitchen" (IDs are long; the
    # dashboard shows the last 12 characters to copy from).
    device_names: Annotated[dict[str, str], NoDecode] = Field(default_factory=dict)

    # Resource limits (keep memory flat no matter how long it runs)
    resolver_workers: int = Field(default=2, ge=1, le=8)
    resolver_tasks_per_worker: int = Field(default=25, ge=1, le=1000)
    stream_link_ttl_hours: int = Field(default=12, ge=1, le=48)

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

    @field_validator("device_names", mode="before")
    @classmethod
    def _parse_names(cls, v: object) -> object:
        if isinstance(v, str):
            pairs = [p.split("=", 1) for p in v.split(",") if "=" in p]
            return {k.strip(): n.strip() for k, n in pairs if k.strip() and n.strip()}
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
        return v

    @property
    def base_url(self) -> str:
        return str(self.public_url).rstrip("/")

    @cached_property
    def stream_secret(self) -> bytes:
        """Key that signs stream links. Created on first start and kept in the data folder."""
        path = self.data_dir / "stream.key"
        if path.exists():
            return path.read_bytes()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        path.touch(mode=0o600)
        path.write_bytes(key)
        return key
