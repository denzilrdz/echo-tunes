"""Prometheus metrics, served at ``/metrics`` on the private dashboard port.

Every label has a small fixed set of values (request types, intent names, outcome categories),
never song titles, device IDs or error messages, so the number of time series can't grow.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    PlatformCollector,
    ProcessCollector,
    generate_latest,
)
from prometheus_client.exposition import CONTENT_TYPE_LATEST

from echo_tunes import __version__

CONTENT_TYPE = CONTENT_TYPE_LATEST

KNOWN_INTENTS = frozenset(
    {
        "PlayIntent", "PlayRadioIntent", "PlayLikedIntent", "PlayPlaylistIntent", "PlayMixIntent",
        "LikeIntent", "WhatsPlayingIntent", "AMAZON.PauseIntent", "AMAZON.ResumeIntent",
        "AMAZON.NextIntent", "AMAZON.PreviousIntent", "AMAZON.StopIntent", "AMAZON.CancelIntent",
        "AMAZON.HelpIntent", "AMAZON.FallbackIntent", "AMAZON.StartOverIntent",
        "AMAZON.RepeatIntent", "AMAZON.ShuffleOnIntent", "AMAZON.ShuffleOffIntent",
        "AMAZON.LoopOnIntent", "AMAZON.LoopOffIntent", "AMAZON.NavigateHomeIntent",
    }
)  # fmt: skip


def rejection_reason(message: str) -> str:
    """Map a verification error to one of a few fixed label values."""
    m = message.lower()
    for key, words in (
        ("too_large", ("too large",)),
        ("missing_signature", ("missing",)),
        ("signature", ("signature", "base64", "body is not")),
        ("certificate", ("certificate", "cert")),
        ("timestamp", ("old", "timestamp")),
        ("wrong_skill", ("different skill",)),
    ):
        if any(w in m for w in words):
            return key
    return "other"


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        r = self.registry
        ProcessCollector(registry=r)  # process_resident_memory_bytes, cpu, open fds, ...
        PlatformCollector(registry=r)
        Info("echo_tunes_build", "echo-tunes version", registry=r).info({"version": __version__})
        self.started = time.time()
        Gauge("echo_tunes_start_time_seconds", "When the server started (Unix time)",
              registry=r).set(self.started)  # fmt: skip

        self.alexa_requests = Counter(
            "echo_tunes_alexa_requests_total", "Verified requests from Alexa, by type",
            ["type"], registry=r,
        )  # fmt: skip
        self.alexa_rejected = Counter(
            "echo_tunes_alexa_rejected_total",
            "Requests to /alexa refused (not genuine, too old, other skill, ...)",
            ["reason"], registry=r,
        )  # fmt: skip
        self.intents = Counter(
            "echo_tunes_intents_total", "Voice commands handled", ["intent"], registry=r
        )
        self.songs_started = Counter(
            "echo_tunes_songs_started_total", "Songs an Echo started playing", registry=r
        )
        self.playback_failures = Counter(
            "echo_tunes_playback_failures_total", "Songs an Echo reported it couldn't play",
            registry=r,
        )  # fmt: skip
        self.streams = Counter(
            "echo_tunes_streams_total", "Audio requests from Echos, by outcome",
            ["outcome"], registry=r,
        )  # fmt: skip
        self.stream_bytes = Counter(
            "echo_tunes_stream_bytes_total", "Audio bytes relayed to Echos", registry=r
        )
        self.resolve_seconds = Histogram(
            "echo_tunes_resolve_seconds", "Time to get a song's audio link from YouTube",
            buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 30), registry=r,
        )  # fmt: skip
        self.resolve_failures = Counter(
            "echo_tunes_resolve_failures_total", "Songs whose audio link couldn't be fetched",
            registry=r,
        )  # fmt: skip
        self.youtube_errors = Counter(
            "echo_tunes_youtube_music_errors_total", "Failed YouTube Music searches or lookups",
            registry=r,
        )  # fmt: skip
        self.last_resolve_ok = Gauge(
            "echo_tunes_last_resolve_success_time_seconds",
            "When an audio link was last fetched successfully (Unix time)", registry=r,
        )  # fmt: skip
        self.last_resolve_error = Gauge(
            "echo_tunes_last_resolve_failure_time_seconds",
            "When fetching an audio link last failed (Unix time)", registry=r,
        )  # fmt: skip
        self.last_error_message = ""
        self.last_ok_at = 0.0
        self.last_alexa_at = 0.0
        self.last_error_at = 0.0
        self._gauges: dict[str, Gauge] = {}

    def intent(self, name: str) -> None:
        self.intents.labels(name if name in KNOWN_INTENTS else "other").inc()

    def alexa_request(self, kind: str) -> None:
        self.last_alexa_at = time.time()
        group = (
            kind
            if kind in {"LaunchRequest", "IntentRequest", "SessionEndedRequest"}
            else (kind.split(".")[0] if "." in kind else "other")
        )
        self.alexa_requests.labels(group).inc()

    def resolved(self, seconds: float) -> None:
        self.resolve_seconds.observe(seconds)
        self.last_ok_at = time.time()
        self.last_resolve_ok.set(self.last_ok_at)

    def resolve_failed(self, error: BaseException) -> None:
        self.resolve_failures.inc()
        self.last_error_at = time.time()
        self.last_resolve_error.set(self.last_error_at)
        # first line only, without URLs, for the health endpoint
        text = str(error).splitlines()[0] if str(error) else type(error).__name__
        self.last_error_message = text.split("http")[0].strip()[:200]

    def add_gauge(self, name: str, doc: str, fn: Callable[[], float]) -> None:
        """A gauge computed when scraped (re-pointed if the app is rebuilt, e.g. in tests)."""
        gauge = self._gauges.get(name)
        if gauge is None:
            gauge = self._gauges[name] = Gauge(name, doc, registry=self.registry)
        gauge.set_function(fn)

    def render(self) -> bytes:
        return generate_latest(self.registry)


# One instance for the process; created on import, cheap.
METRICS = Metrics()
