"""Play history: every song an Echo started, kept for a configurable number of days.

Stored in SQLite on disk (never in memory) and pruned automatically, so it can't grow without
bound: ``ECHO_TUNES_HISTORY_DAYS`` (default 15) sets how long rows are kept, 0 turns it off.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from echo_tunes.music.catalog import Track

PRUNE_EVERY = 3600.0  # seconds between automatic clean-ups

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plays (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    device    TEXT NOT NULL,
    video_id  TEXT NOT NULL,
    title     TEXT NOT NULL,
    artist    TEXT NOT NULL,
    duration  INTEGER,
    source    TEXT NOT NULL,
    started   REAL NOT NULL,
    ended     REAL,
    played_ms INTEGER,
    status    TEXT NOT NULL DEFAULT 'playing'
);
CREATE INDEX IF NOT EXISTS plays_started ON plays(started);
CREATE INDEX IF NOT EXISTS plays_device ON plays(device, started);
"""

STATUSES = ("playing", "finished", "stopped", "skipped", "failed")


class History:
    def __init__(self, path: Path | str, days: int, clock: Callable[[], float] = time.time) -> None:
        self.days = days
        self._clock = clock
        self._lock = threading.Lock()
        self._last_prune = 0.0
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        # WAL + NORMAL: no disk flush per write (a power cut can lose the last few plays, but
        # never corrupts the file). Every Alexa event writes, and SD cards are slow to flush.
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(_SCHEMA)
        self.prune()

    @property
    def enabled(self) -> bool:
        return self.days > 0

    # --- writing ----------------------------------------------------------------------------
    def started(self, device: str, track: Track, source: str) -> None:
        if not self.enabled:
            return
        now = self._clock()
        with self._lock:
            # Anything still "playing" on this Echo was cut short by this song.
            self._db.execute(
                "UPDATE plays SET status='skipped', ended=?,"
                " played_ms=CAST((? - started) * 1000 AS INTEGER)"
                " WHERE device=? AND status='playing'",
                (now, now, device),
            )
            self._db.execute(
                "INSERT INTO plays(device, video_id, title, artist, duration, source, started)"
                " VALUES (?,?,?,?,?,?,?)",
                (device, track.video_id, track.title, track.artist, track.duration, source, now),
            )
        if now - self._last_prune > PRUNE_EVERY:
            self.prune()

    def resumed(self, device: str, video_id: str) -> bool:
        """Reopen the paused row for this song instead of counting a second play."""
        if not self.enabled:
            return False
        with self._lock:
            cur = self._db.execute(
                "UPDATE plays SET status='playing', ended=NULL"
                " WHERE id = (SELECT id FROM plays WHERE device=? ORDER BY started DESC LIMIT 1)"
                " AND video_id=? AND status='stopped'",
                (device, video_id),
            )
            return cur.rowcount > 0

    def ended(self, device: str, video_id: str, status: str, offset_ms: int | None) -> None:
        """Close the open row for this song (finished, stopped/paused or failed)."""
        if not self.enabled or status not in STATUSES:
            return
        now = self._clock()
        with self._lock:
            self._db.execute(
                "UPDATE plays SET status=?, ended=?,"
                " played_ms=COALESCE(?, CAST((? - started) * 1000 AS INTEGER))"
                " WHERE id = (SELECT id FROM plays WHERE device=? AND video_id=?"
                "             AND status='playing' ORDER BY started DESC LIMIT 1)",
                (status, now, offset_ms, now, device, video_id),
            )

    def prune(self) -> int:
        """Delete rows older than the retention window; returns how many were removed."""
        now = self._clock()
        self._last_prune = now
        with self._lock:
            if not self.enabled:
                cur = self._db.execute("DELETE FROM plays")
            else:
                cur = self._db.execute(
                    "DELETE FROM plays WHERE started < ?", (now - self.days * 86400,)
                )
            return cur.rowcount

    # --- reading ----------------------------------------------------------------------------
    def recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        device: str | None = None,
        query: str | None = None,
        days: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM plays WHERE started >= ?"
        args: list[Any] = [self._since(days)]
        if device:
            sql += " AND device = ?"
            args.append(device)
        if query:
            sql += " AND (title LIKE ? ESCAPE '\\' OR artist LIKE ? ESCAPE '\\')"
            like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            args += [like, like]
        sql += " ORDER BY started DESC LIMIT ? OFFSET ?"
        args += [max(1, min(limit, 500)), max(0, offset)]
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args)]

    def stats(
        self, days: int | None = None, device: str | None = None, utc_offset_min: int | None = None
    ) -> dict[str, Any]:
        """Totals, top songs/artists and plays per day.

        Days are counted in the viewer's time zone (``utc_offset_min``, minutes east of UTC,
        from the browser), else the server's: in Docker that's UTC, which would move evening
        plays west of UTC to the next day.
        """
        since = self._since(days)
        if utc_offset_min is None:
            day_expr, day_args = "date(started, 'unixepoch', 'localtime')", []
        else:
            day_expr, day_args = "date(started + ?, 'unixepoch')", [utc_offset_min * 60]
        where = "started >= ?" + (" AND device = ?" if device else "")
        args: list[Any] = [since] + ([device] if device else [])
        with self._lock:
            row = self._db.execute(
                f"SELECT COUNT(*) AS plays, COALESCE(SUM(played_ms), 0) AS played_ms,"  # noqa: S608
                f" COUNT(DISTINCT video_id) AS songs, COUNT(DISTINCT artist) AS artists"
                f" FROM plays WHERE {where}",
                args,
            ).fetchone()
            top_songs = self._db.execute(
                f"SELECT video_id, title, artist, COUNT(*) AS plays FROM plays"  # noqa: S608
                f" WHERE {where} GROUP BY video_id ORDER BY plays DESC, MAX(started) DESC"
                f" LIMIT 10",
                args,
            ).fetchall()
            top_artists = self._db.execute(
                f"SELECT artist, COUNT(*) AS plays FROM plays WHERE {where} AND artist != ''"  # noqa: S608
                f" GROUP BY artist ORDER BY plays DESC LIMIT 10",
                args,
            ).fetchall()
            per_day = self._db.execute(
                f"SELECT {day_expr} AS day, COUNT(*) AS plays,"  # noqa: S608
                f" COALESCE(SUM(played_ms), 0) AS played_ms FROM plays WHERE {where}"
                f" GROUP BY day ORDER BY day",
                [*day_args, *args],
            ).fetchall()
        return {
            "days": days or self.days,
            "plays": row["plays"],
            "listened_minutes": round(row["played_ms"] / 60000),
            "songs": row["songs"],
            "artists": row["artists"],
            "top_songs": [dict(r) for r in top_songs],
            "top_artists": [dict(r) for r in top_artists],
            "per_day": [dict(r) for r in per_day],
        }

    def count(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM plays").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _since(self, days: int | None) -> float:
        keep = self.days if not days or days > self.days else days
        return self._clock() - max(keep, 1) * 86400
