"""The dashboard's player: parsing YouTube Music answers, browsing, and the guarded actions."""

from __future__ import annotations

import base64
from typing import Any

import pytest
from fastapi.testclient import TestClient

from echo_tunes.alexa.skill import Skill
from echo_tunes.dashboard import DashboardDeps, create_dashboard
from echo_tunes.history import History
from echo_tunes.music import browse
from echo_tunes.music.catalog import YTMusicCatalog

from .conftest import DEVICE, directives, event, intent, song

SHORT = DEVICE[-12:]
THUMB = [{"url": "https://lh3.googleusercontent.com/a=w120", "width": 120},
         {"url": "https://lh3.googleusercontent.com/a=w544", "width": 544}]  # fmt: skip


# --- parsing --------------------------------------------------------------------------------
def test_parse_each_kind() -> None:
    song_ = browse.parse(
        {
            "resultType": "song",
            "videoId": "3HlzLiCL9Xs",
            "title": "Jaan",
            "duration_seconds": 239,
            "artists": [{"name": "Arijit Singh"}],
            "thumbnails": THUMB,
        }
    )
    assert song_ == browse.Item("song", "3HlzLiCL9Xs", "Jaan", "Arijit Singh", THUMB[1]["url"], 239)
    album = browse.parse(
        {"resultType": "album", "browseId": "MPREb_x1", "title": "A", "year": "2023"}
    )
    assert album is not None and album.kind == "album" and album.subtitle == "2023"
    artist = browse.parse({"resultType": "artist", "artist": "Arijit", "browseId": "UCabc"})
    assert artist is not None and (artist.kind, artist.title) == ("artist", "Arijit")
    chart_artist = browse.parse({"browseId": "UCdef", "title": "Someone", "rank": "1"})
    assert chart_artist is not None and chart_artist.kind == "artist"
    pl = browse.parse(
        {"resultType": "playlist", "browseId": "VLPLabc123", "title": "P", "author": "me"}
    )
    assert pl is not None and (pl.kind, pl.id, pl.subtitle) == ("playlist", "PLabc123", "me")
    home_pl = browse.parse({"playlistId": "RDCLAK5uy_x", "title": "Mix", "description": "d"})
    assert home_pl is not None and home_pl.kind == "playlist"


@pytest.mark.parametrize(
    "raw",
    [
        {"videoId": "../../etc", "title": "x"},
        {"videoId": "3HlzLiCL9Xs", "isAvailable": False},
        {"resultType": "album", "browseId": "MPRE<script>"},
        {"playlistId": "a b c"},
        "not a dict",
    ],
)
def test_parse_drops_bad_items(raw: Any) -> None:
    assert browse.parse(raw) is None


def test_artwork_only_from_googles_image_hosts() -> None:
    assert browse.image([{"url": "https://evil.example/x.jpg", "width": 500}]) is None
    assert browse.image([{"url": "http://i.ytimg.com/vi/x/1.jpg", "width": 500}]) is None
    assert browse.image(THUMB, prefer=300) == THUMB[1]["url"]
    assert browse.image(THUMB, prefer=100) == THUMB[0]["url"]


# --- catalog browsing with a fake ytmusicapi -------------------------------------------------
class FakeYT:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, q: str, filter: str, limit: int) -> list[dict[str, Any]]:
        self.calls.append(f"search:{filter}")
        return [{"resultType": "song", "videoId": "3HlzLiCL9Xs", "title": q}]

    def get_charts(self, country: str) -> dict[str, Any]:
        self.calls.append(f"charts:{country}")
        return {"videos": [{"playlistId": "PLtop", "title": "Top songs"}],
                "artists": [{"browseId": "UCx", "title": "A", "rank": "1"}]}  # fmt: skip

    def get_mood_categories(self) -> dict[str, Any]:
        return {"Moods & moments": [{"title": "Chill", "params": "ggMPOg1uX1"}, {"title": "x"}]}

    def get_mood_playlists(self, params: str) -> list[dict[str, Any]]:
        return [{"playlistId": "RDCLAK5uy_chill", "title": "Chill"}]

    def get_home(self, limit: int) -> list[dict[str, Any]]:
        return [{"title": "Quick picks", "contents": [{"videoId": "3HlzLiCL9Xs", "title": "s"}]},
                {"title": "Empty", "contents": []}]  # fmt: skip

    def get_playlist(self, pid: str, limit: int) -> dict[str, Any]:
        return {"title": "Top songs", "tracks": [{"videoId": "3HlzLiCL9Xs", "title": "s"}]}

    def get_album(self, bid: str) -> dict[str, Any]:
        return {"title": "Album", "artists": [{"name": "Band"}],
                "tracks": [{"videoId": "3HlzLiCL9Xs", "title": "s", "artists": []}]}  # fmt: skip

    def get_artist(self, cid: str) -> dict[str, Any]:
        return {"name": "Band", "songs": {"results": [{"videoId": "3HlzLiCL9Xs", "title": "s"}]}}

    def get_watch_playlist(self, **kw: Any) -> dict[str, Any]:
        return {"tracks": [{"videoId": "3HlzLiCL9Xs", "title": "radio"}]}


async def test_catalog_browsing_is_parsed_and_cached() -> None:
    yt = FakeYT()
    cat = YTMusicCatalog(yt, signed_in=False)
    first = await cat.search_items("hello", "song")
    again = await cat.search_items("Hello ", "song")
    assert first == again and yt.calls.count("search:songs") == 1
    charts = await cat.charts("in")
    assert charts["playlists"][0].id == "PLtop" and charts["artists"][0].kind == "artist"
    assert "charts:IN" in yt.calls
    await cat.charts("<bad>")
    assert "charts:ZZ" in yt.calls
    moods = await cat.moods()
    assert moods == [
        {"title": "Moods & moments", "categories": [{"title": "Chill", "params": "ggMPOg1uX1"}]}
    ]
    assert (await cat.mood_playlists("ggMPOg1uX1"))[0].id == "RDCLAK5uy_chill"
    assert await cat.mood_playlists("bad params!") == []
    assert [s["title"] for s in await cat.home()] == ["Quick picks"]
    title, tracks = await cat.items_of("album", "MPREb_x1")
    assert title == "Album" and tracks[0].artist == "Band"
    assert (await cat.items_of("artist", "UCx"))[0] == "Band"
    assert (await cat.items_of("playlist", "RDCLAK5uy_chill"))[1][0].title == "radio"
    with pytest.raises(ValueError):
        await cat.items_of("playlist", "../x")


# --- the dashboard API -------------------------------------------------------------------------
def client(skill: Skill, password: str | None = "pw", **kw: Any) -> TestClient:  # noqa: S107
    if skill.history is None:
        skill.history = History(":memory:", 15)
    deps = DashboardDeps(
        store=skill.store, history=skill.history, signed_in=lambda: False, password=password,
        catalog=YTMusicCatalog(FakeYT(), signed_in=False), skill=skill, **kw,
    )  # fmt: skip
    headers = {"Sec-Fetch-Site": "same-origin"}
    if password:
        headers["Authorization"] = (
            "Basic " + base64.b64encode(f"admin:{password}".encode()).decode()
        )
    return TestClient(create_dashboard(deps), base_url="http://localhost:8081", headers=headers)


TRACK = {"video_id": "vid00000077", "title": "Picked", "artist": "Someone", "duration": 180}


async def start(skill: Skill) -> str:
    resp = await skill.handle(intent("PlayIntent", "x"))
    await skill.wait_background()
    tok = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", tok))
    return tok


def test_browsing_endpoints(skill: Skill) -> None:
    c = client(skill, password=None)
    assert c.get("/api/search", params={"q": "x", "kind": "album"}).status_code == 200
    assert c.get("/api/search", params={"q": "x", "kind": "video"}).status_code == 422
    assert c.get("/api/browse/home").json()["sections"][0]["title"] == "Quick picks"
    ex = c.get("/api/browse/explore").json()
    assert ex["charts"][0]["title"] == "Top songs" and ex["moods"]
    assert c.get("/api/browse/tracks", params={"kind": "playlist", "id": "PLtop"}).json()["tracks"]
    assert c.get("/api/browse/library").status_code == 409  # not signed in
    assert c.get("/api/player").json()["actions"] is False  # no password


def test_actions_need_a_password(skill: Skill) -> None:
    c = client(skill, password=None)
    r = c.post("/api/play/stream-link", json={"video_id": "vid00000077"})
    assert r.status_code == 403 and "ECHO_TUNES_DASHBOARD_PASSWORD" in r.text
    assert c.post("/api/history/clear", json={}).status_code == 403


def test_actions_refuse_cross_site_and_forms(skill: Skill) -> None:
    c = client(skill)
    url, body = "/api/play/stream-link", {"video_id": "vid00000077"}
    assert c.post(url, json=body).status_code == 200
    assert c.post(url, json=body, headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    assert c.post(url, json=body, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post(url, json=body, headers={"Origin": "http://localhost:8081"}).status_code == 200
    form = c.post(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert form.status_code == 415
    assert c.get(url).status_code == 405


async def test_play_in_browser_and_history(skill: Skill) -> None:
    c = client(skill)
    link = c.post("/api/play/stream-link", json={"video_id": "vid00000077"}).json()["url"]
    assert link.startswith("https://music.example.com/stream/vid00000077.")
    assert c.post("/api/play/played", json={"track": TRACK}).status_code == 200
    plays = c.get("/api/history").json()["plays"]
    assert plays[0]["title"] == "Picked"
    # Audit: browser plays showed as "Echo ...rowser" and couldn't be filtered.
    assert plays[0]["device"] == "browser" and plays[0]["device_name"] == "Web player"
    assert {"id": "browser", "name": "Web player"} in c.get("/api/devices").json()
    mine = c.get("/api/history", params={"device": "browser"}).json()["plays"]
    assert [p["title"] for p in mine] == ["Picked"]
    assert c.get("/api/stats", params={"device": "browser"}).json()["plays"] == 1
    bad = c.post("/api/play/echo", json={"device": "browser", "mode": "now", "tracks": [TRACK]})
    assert bad.status_code == 404
    assert c.post("/api/history/clear", json={}).json() == {"removed": 1}
    assert c.get("/api/history").json()["plays"] == []


async def test_queue_on_an_echo_and_jump_to_it(skill: Skill) -> None:
    c = client(skill)
    tok = await start(skill)
    nearly = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", tok))
    old_next = directives(nearly)[0]["audioItem"]["stream"]["token"]  # already on the Echo
    r = c.post("/api/play/echo", json={"device": SHORT, "mode": "now", "tracks": [TRACK]})
    assert r.status_code == 200 and r.json()["placed"] == 1
    state = skill.store.get(DEVICE)
    assert state.tracks[state.index + 1].video_id == "vid00000077" and state.pending
    # The Echo starts the song it had lined up; the reply switches to the chosen one.
    resp = await skill.handle(event("AudioPlayer.PlaybackStarted", old_next))
    [play] = directives(resp)
    assert play["playBehavior"] == "REPLACE_ALL"
    assert play["audioItem"]["metadata"]["title"] == "Picked"
    resp = await skill.handle(
        event("AudioPlayer.PlaybackStarted", play["audioItem"]["stream"]["token"])
    )
    assert not directives(resp) and not skill.store.get(DEVICE).pending


async def test_queue_next_and_at_the_end(skill: Skill) -> None:
    c = client(skill)
    await start(skill)
    other = {**TRACK, "video_id": "vid00000088", "title": "Last"}
    c.post("/api/play/echo", json={"device": SHORT, "mode": "queue", "tracks": [other]})
    c.post("/api/play/echo", json={"device": SHORT, "mode": "next", "tracks": [TRACK]})
    state = skill.store.get(DEVICE)
    assert state.tracks[1].title == "Picked" and state.tracks[-1].title == "Last"
    assert state.current is not None and state.current.title == "Song 1" and not state.pending
    unknown = c.post("/api/play/echo", json={"device": "nope", "mode": "next", "tracks": [TRACK]})
    assert unknown.status_code == 404
    bad_track = {**TRACK, "video_id": "../../etc/x"}
    bad = c.post("/api/play/echo", json={"device": SHORT, "mode": "next", "tracks": [bad_track]})
    assert bad.status_code == 422


def title(d: dict[str, Any]) -> str:
    return str(d["audioItem"]["metadata"]["title"])


def tok(d: dict[str, Any]) -> str:
    return str(d["audioItem"]["stream"]["token"])


async def test_play_next_after_the_echo_lined_up_a_song_still_plays(skill: Skill) -> None:
    """Audit: "Play next" went before the song the Echo had already queued; when that song
    started, the pick was behind the current position and never played."""
    c = client(skill)
    first = await start(skill)
    nearly = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", first))
    [enq_b] = directives(nearly)
    assert enq_b["playBehavior"] == "ENQUEUE"
    r = c.post("/api/play/echo", json={"device": SHORT, "mode": "next", "tracks": [TRACK]})
    assert r.status_code == 200 and r.json()["placed"] == 1
    await skill.handle(event("AudioPlayer.PlaybackFinished", first))
    started_b = await skill.handle(event("AudioPlayer.PlaybackStarted", tok(enq_b)))
    assert not directives(started_b)
    nearly_b = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", tok(enq_b)))
    [enq_x] = directives(nearly_b)
    assert enq_x["playBehavior"] == "ENQUEUE" and title(enq_x) == "Picked"


async def test_play_next_before_anything_is_lined_up_goes_right_after(skill: Skill) -> None:
    c = client(skill)
    first = await start(skill)
    c.post("/api/play/echo", json={"device": SHORT, "mode": "next", "tracks": [TRACK]})
    [enq] = directives(await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", first)))
    assert title(enq) == "Picked"


async def test_old_play_now_pick_does_not_hijack_a_new_voice_request(skill: Skill) -> None:
    """Audit: a "Play now" pick survived "play my liked songs" (and next/previous/start over),
    and the first PlaybackStarted of the new song jumped to the old pick."""
    skill.catalog.signed_in = True  # type: ignore[misc]
    c = client(skill)
    first = await start(skill)
    await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", first))
    c.post("/api/play/echo", json={"device": SHORT, "mode": "now", "tracks": [TRACK]})
    resp = await skill.handle(intent("PlayLikedIntent"))
    [play] = directives(resp)
    started = await skill.handle(event("AudioPlayer.PlaybackStarted", tok(play)))
    assert not directives(started) and not skill.store.get(DEVICE).pending

    for command in ("AMAZON.NextIntent", "AMAZON.PreviousIntent", "AMAZON.StartOverIntent"):
        c.post("/api/play/echo", json={"device": SHORT, "mode": "now", "tracks": [TRACK]})
        [play] = directives(await skill.handle(intent(command)))
        started = await skill.handle(event("AudioPlayer.PlaybackStarted", tok(play)))
        assert not directives(started), command


async def test_resume_plays_a_pick_made_while_paused(skill: Skill) -> None:
    c = client(skill)
    first = await start(skill)
    await skill.handle(intent("AMAZON.PauseIntent"))
    await skill.handle(event("AudioPlayer.PlaybackStopped", first, offsetInMilliseconds=9_000))
    c.post("/api/play/echo", json={"device": SHORT, "mode": "now", "tracks": [TRACK]})
    [play] = directives(await skill.handle(intent("AMAZON.ResumeIntent")))
    assert title(play) == "Picked" and play["audioItem"]["stream"]["offsetInMilliseconds"] == 0


async def test_a_failed_play_now_pick_is_skipped_not_retried(skill: Skill) -> None:
    """Audit: a picked song that failed was jumped to again (pending was still set)."""
    c = client(skill)
    first = await start(skill)
    c.post("/api/play/echo", json={"device": SHORT, "mode": "now", "tracks": [TRACK]})
    [enq] = directives(await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", first)))
    assert title(enq) == "Picked"
    await skill.handle(event("AudioPlayer.PlaybackFinished", first))
    failed = await skill.handle(
        event("AudioPlayer.PlaybackFailed", tok(enq), error={"type": "MEDIA_ERROR_UNKNOWN"})
    )
    [play] = directives(failed)
    assert title(play) != "Picked"
    assert not skill.store.get(DEVICE).pending


async def test_picks_while_shuffled_keep_the_original_order(skill: Skill) -> None:
    """Audit: a dashboard insert with shuffle on saved the shuffled order as the original, so
    shuffle off no longer restored it."""
    c = client(skill)
    await start(skill)
    original = [t.video_id for t in skill.store.get(DEVICE).tracks]
    await skill.handle(intent("AMAZON.ShuffleOnIntent"))
    c.post("/api/play/echo", json={"device": SHORT, "mode": "next", "tracks": [TRACK]})
    other = {**TRACK, "video_id": "vid00000088", "title": "Last"}
    c.post("/api/play/echo", json={"device": SHORT, "mode": "queue", "tracks": [other]})
    await skill.handle(intent("AMAZON.ShuffleOffIntent"))
    after = [t.video_id for t in skill.store.get(DEVICE).tracks]
    assert after == [original[0], "vid00000077", *original[1:], "vid00000088"]


async def test_adding_to_a_full_queue_reports_what_fit(skill: Skill) -> None:
    """Audit: "Add to end" on a full queue said every song was added after dropping them."""
    c = client(skill)
    await start(skill)
    many = [{**TRACK, "video_id": f"x{i:010d}", "title": f"T{i}"} for i in range(60)]
    r = c.post("/api/play/echo", json={"device": SHORT, "mode": "queue", "tracks": many}).json()
    state = skill.store.get(DEVICE)
    fit = sum(1 for t in state.tracks if t.video_id.startswith("x"))
    assert r["placed"] == fit < 60 and "full" in r["note"]


async def test_queue_on_an_echo_that_has_nothing_to_play(skill: Skill) -> None:
    from echo_tunes.player.state import PlayerState

    skill.store.put(DEVICE, PlayerState())
    r = client(skill).post(
        "/api/play/echo", json={"device": SHORT, "mode": "now", "tracks": [TRACK]}
    )
    assert r.status_code == 409 and "by voice first" in r.text


@pytest.mark.parametrize(
    ("method", "path", "params"),
    [
        ("search", "/api/search", {"q": "x"}),
        ("get_home", "/api/browse/home", {}),
        ("get_charts", "/api/browse/explore", {}),
        ("get_playlist", "/api/browse/tracks", {"kind": "playlist", "id": "PLtop"}),
    ],
)
def test_youtube_errors_become_502(skill: Skill, method: str, path: str, params: dict) -> None:  # type: ignore[type-arg]
    yt = FakeYT()

    def boom(*a: Any, **kw: Any) -> None:
        raise ConnectionError("YouTube Music unreachable")

    setattr(yt, method, boom)
    if skill.history is None:
        skill.history = History(":memory:", 15)
    deps = DashboardDeps(
        store=skill.store, history=skill.history, signed_in=lambda: False,
        catalog=YTMusicCatalog(yt, signed_in=False), skill=skill,
    )  # fmt: skip
    c = TestClient(create_dashboard(deps), base_url="http://localhost:8081")
    r = c.get(path, params=params)
    assert r.status_code == 502 and "didn't answer" in r.text


def test_not_signed_in_and_bad_ids_are_409_and_422(skill: Skill) -> None:
    c = client(skill, password=None)
    assert c.get("/api/browse/tracks", params={"kind": "playlist", "id": "LM"}).status_code == 409
    bad = c.get("/api/browse/tracks", params={"kind": "song", "id": "bad id!"})
    assert bad.status_code == 422


async def test_skip_is_off_unless_enabled(skill: Skill) -> None:
    await start(skill)
    assert client(skill).post("/api/play/skip", json={"device": SHORT}).status_code == 403


async def test_experimental_skip_cuts_the_stream_and_plays_the_next(skill: Skill) -> None:
    from echo_tunes.stream import StreamSlots

    slots = StreamSlots()
    c = client(skill, experimental_skip=True, cut_stream=slots.cut)
    tok = await start(skill)
    key = "vid00000001.123.sig"
    assert slots.acquire(key) is None
    r = c.post("/api/play/skip", json={"device": SHORT}).json()
    assert r["cut"] == 1 and slots.abort_event(key).is_set()
    assert slots.acquire("vid00000001.456.sig") == "cut"  # the Echo's retry is refused
    resp = await skill.handle(
        event("AudioPlayer.PlaybackFailed", tok, error={"type": "MEDIA_ERROR_UNKNOWN"})
    )
    [play] = directives(resp)
    assert (
        play["playBehavior"] == "REPLACE_ALL" and play["audioItem"]["metadata"]["title"] != "Song 1"
    )


def test_queue_insert_keeps_the_current_song() -> None:
    from echo_tunes.player.state import PlayerState

    s = PlayerState()
    s.replace([song(i) for i in range(5)], 10)
    s.index = 2
    s.insert([song(4), song(0), song(2)], at_end=False, max_len=10)
    assert [t.video_id[-1] for t in s.tracks] == ["1", "2", "4", "0", "3"]
    assert s.current == song(2)
    s.insert([song(9)], at_end=True, max_len=5)
    assert len(s.tracks) == 5 and s.current == song(2) and s.tracks[-1] == song(9)


# --- installable app (PWA) -----------------------------------------------------------------
def test_manifest_and_service_worker_follow_the_settings(skill: Skill, tmp_path: Any) -> None:
    c = client(skill, password=None)
    m = c.get("/manifest.webmanifest")
    assert m.headers["content-type"].startswith("application/manifest+json")
    assert m.json()["name"] == "echo-tunes" and m.json()["display"] == "standalone"
    assert any(i.get("purpose") == "maskable" for i in m.json()["icons"])
    sw = c.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    assert c.get("/app-icon.png").status_code == 404
    for icon in ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"):
        assert c.get(f"/static/{icon}").status_code == 200

    png = tmp_path / "mine.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
    c = client(skill, password=None, app_name="Our <Music>", app_color="#aa3300", app_icon=png)
    m = c.get("/manifest.webmanifest").json()
    assert m["name"] == "Our <Music>" and m["theme_color"] == "#aa3300"
    assert m["icons"][0]["src"] == "/app-icon.png"
    assert c.get("/app-icon.png").content.startswith(b"\x89PNG")
    page = c.get("/").text
    assert "<title>Our &lt;Music&gt;</title>" in page and '"#aa3300" data-theme-color' in page
