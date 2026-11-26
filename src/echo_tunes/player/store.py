"""Keeps each Echo's player state in a small SQLite file instead of in memory."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from echo_tunes.player.state import PlayerState

MAX_DEVICES = 50


class StateStore:
    def __init__(self, path: Path | str, max_devices: int = MAX_DEVICES) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS players ("
            " device TEXT PRIMARY KEY, state TEXT NOT NULL, updated REAL NOT NULL)"
        )
        self._lock = threading.Lock()
        self._max_devices = max_devices

    def get(self, device: str) -> PlayerState:
        with self._lock:
            row = self._db.execute("SELECT state FROM players WHERE device=?", (device,)).fetchone()
        return PlayerState.from_dict(json.loads(row[0])) if row else PlayerState()

    def put(self, device: str, state: PlayerState) -> None:
        payload = json.dumps(state.to_dict(), separators=(",", ":"))
        with self._lock:
            self._db.execute(
                "INSERT INTO players(device, state, updated) VALUES (?,?,?)"
                " ON CONFLICT(device) DO UPDATE SET state=excluded.state, updated=excluded.updated",
                (device, payload, time.time()),
            )
            # Forget the least recently used devices beyond the limit.
            self._db.execute(
                "DELETE FROM players WHERE device NOT IN"
                " (SELECT device FROM players ORDER BY updated DESC LIMIT ?)",
                (self._max_devices,),
            )

    def all(self) -> list[tuple[str, PlayerState, float]]:
        """Every known Echo (at most MAX_DEVICES), most recently active first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT device, state, updated FROM players ORDER BY updated DESC"
            ).fetchall()
        return [(d, PlayerState.from_dict(json.loads(s)), u) for d, s, u in rows]

    def count(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM players").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._db.close()
