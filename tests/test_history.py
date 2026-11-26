from __future__ import annotations

from pathlib import Path

from echo_tunes.history import History

from .conftest import song

DAY = 86400.0


class Clock:
    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


def make(days: int = 15) -> tuple[History, Clock]:
    clock = Clock()
    return History(":memory:", days, clock=clock), clock


def test_records_a_play_and_its_end() -> None:
    h, clock = make()
    h.started("echo-1", song(1), 'Asked for "song 1"')
    clock.t += 120
    h.ended("echo-1", song(1).video_id, "finished", 200_000)
    [row] = h.recent()
    assert row["status"] == "finished" and row["played_ms"] == 200_000
    assert row["source"] == 'Asked for "song 1"' and row["title"] == "Song 1"


def test_a_new_song_marks_the_unfinished_one_skipped() -> None:
    h, clock = make()
    h.started("echo-1", song(1), "x")
    clock.t += 30
    h.started("echo-1", song(2), "x")
    older, newer = sorted(h.recent(), key=lambda r: r["started"])
    assert older["status"] == "skipped" and older["played_ms"] == 30_000
    assert newer["status"] == "playing"


def test_other_echos_are_independent() -> None:
    h, _ = make()
    h.started("echo-1", song(1), "x")
    h.started("echo-2", song(2), "x")
    assert {r["status"] for r in h.recent()} == {"playing"}
    assert [r["title"] for r in h.recent(device="echo-2")] == ["Song 2"]


def test_retention_prunes_old_rows() -> None:
    h, clock = make(days=15)
    h.started("echo-1", song(1), "x")
    clock.t += 16 * DAY
    h.started("echo-1", song(2), "x")  # triggers the hourly prune
    assert [r["title"] for r in h.recent(days=3650)] == ["Song 2"]
    assert h.count() == 1


def test_history_off_keeps_nothing() -> None:
    h, _ = make(days=0)
    h.started("echo-1", song(1), "x")
    assert h.count() == 0 and not h.enabled


def test_search_is_literal_and_paginates() -> None:
    h, clock = make()
    for i in range(30):
        h.started("echo-1", song(i), "x")
        clock.t += 10
    assert len(h.recent(limit=10)) == 10
    assert h.recent(limit=10)[0]["title"] == "Song 29"
    assert len(h.recent(limit=10, offset=25)) == 5
    assert [r["title"] for r in h.recent(query="Song 7")] == ["Song 7"]
    assert h.recent(query="%") == []  # wildcards are matched literally


def test_stats() -> None:
    h, clock = make()
    for i in (1, 1, 2):
        h.started("echo-1", song(i), "x")
        clock.t += 60
        h.ended("echo-1", song(i).video_id, "finished", 60_000)
    s = h.stats(days=7)
    assert s["plays"] == 3 and s["songs"] == 2 and s["listened_minutes"] == 3
    assert s["top_songs"][0]["title"] == "Song 1" and s["top_songs"][0]["plays"] == 2
    assert sum(d["plays"] for d in s["per_day"]) == 3


def test_persists_on_disk(tmp_path: Path) -> None:
    h = History(tmp_path / "h.sqlite3", 15)
    h.started("echo-1", song(1), "x")
    h.close()
    assert History(tmp_path / "h.sqlite3", 15).count() == 1
