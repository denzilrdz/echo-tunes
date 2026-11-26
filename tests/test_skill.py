from __future__ import annotations

import asyncio

from echo_tunes import tokens
from echo_tunes.alexa.skill import Skill

from .conftest import DEVICE, SECRET, directives, envelope, event, intent, song


async def start(skill: Skill, query: str = "tum hi ho") -> dict:
    resp = await skill.handle(intent("PlayIntent", query))
    await skill.wait_background()  # the radio is fetched after answering Alexa
    return resp


async def test_launch_asks_what_to_play(skill: Skill) -> None:
    resp = await skill.handle(envelope({"type": "LaunchRequest"}))
    assert "What would you like to play" in resp["response"]["outputSpeech"]["ssml"]
    assert resp["response"]["shouldEndSession"] is False


async def test_play_intent_plays_song_and_builds_radio_queue(skill: Skill) -> None:
    resp = await start(skill)
    [play] = directives(resp)
    assert play["type"] == "AudioPlayer.Play" and play["playBehavior"] == "REPLACE_ALL"
    stream = play["audioItem"]["stream"]
    assert stream["url"].startswith("https://music.example.com/stream/")
    video = tokens.check(SECRET, stream["url"].rsplit("/", 1)[1].removesuffix(".m4a"))
    assert video == "vid00000001"
    assert "Playing Song 1 by Artist 1" in resp["response"]["outputSpeech"]["ssml"]
    state = skill.store.get(DEVICE)
    assert len(state.tracks) == 10  # seed + 9 radio songs, seed de-duplicated
    assert len({t.video_id for t in state.tracks}) == 10
    assert "vid00000001" in skill.resolver.warmed  # type: ignore[attr-defined]


async def test_unknown_song(skill: Skill) -> None:
    resp = await start(skill, "nothing at all")
    assert "couldn't find" in resp["response"]["outputSpeech"]["ssml"]
    assert not directives(resp)


async def test_empty_query_asks_again(skill: Skill) -> None:
    resp = await skill.handle(intent("PlayIntent", ""))
    assert resp["response"]["shouldEndSession"] is False


async def test_nearly_finished_enqueues_next_with_expected_token(skill: Skill) -> None:
    resp = await start(skill)
    token = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", token))
    resp = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", token))
    [enq] = directives(resp)
    assert enq["playBehavior"] == "ENQUEUE"
    assert enq["audioItem"]["stream"]["expectedPreviousToken"] == token
    assert "outputSpeech" not in resp["response"]


async def test_queue_end_tops_up_with_radio(skill: Skill) -> None:
    await start(skill)
    state = skill.store.get(DEVICE)
    last = len(state.tracks) - 1
    token = state.token(last)
    resp = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", token))
    assert directives(resp), "should keep playing with more radio songs"
    assert len(skill.store.get(DEVICE).tracks) > last + 1


async def test_next_previous_and_buttons(skill: Skill) -> None:
    await start(skill)
    resp = await skill.handle(intent("AMAZON.NextIntent"))
    assert skill.store.get(DEVICE).index == 1
    assert directives(resp)[0]["playBehavior"] == "REPLACE_ALL"
    await skill.handle(envelope({"type": "PlaybackController.PreviousCommandIssued"}))
    assert skill.store.get(DEVICE).index == 0
    resp = await skill.handle(envelope({"type": "PlaybackController.NextCommandIssued"}))
    assert "outputSpeech" not in resp["response"]  # buttons must not speak


async def test_pause_and_resume_at_offset(skill: Skill) -> None:
    resp = await start(skill)
    token = directives(resp)[0]["audioItem"]["stream"]["token"]
    resp = await skill.handle(intent("AMAZON.PauseIntent"))
    assert directives(resp)[0]["type"] == "AudioPlayer.Stop"
    await skill.handle(event("AudioPlayer.PlaybackStopped", token, offsetInMilliseconds=42_000))
    resp = await skill.handle(intent("AMAZON.ResumeIntent"))
    assert directives(resp)[0]["audioItem"]["stream"]["offsetInMilliseconds"] == 42_000


async def test_stale_tokens_are_ignored(skill: Skill) -> None:
    resp = await start(skill)
    old = directives(resp)[0]["audioItem"]["stream"]["token"]
    await start(skill, "another song")  # replaces the queue
    resp = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", old))
    assert not directives(resp)


async def test_failed_song_skips_but_gives_up_after_three(skill: Skill) -> None:
    await start(skill)
    for i in range(3):
        state = skill.store.get(DEVICE)
        resp = await skill.handle(
            event(
                "AudioPlayer.PlaybackFailed", state.token(), error={"type": "MEDIA_ERROR_UNKNOWN"}
            )
        )
        if i < 2:
            assert directives(resp), "should skip to the next song"
        else:
            assert not directives(resp), "should stop after three failures in a row"
    assert len(skill.resolver.invalidated) == 3  # type: ignore[attr-defined]


async def test_whats_playing(skill: Skill) -> None:
    await start(skill)
    resp = await skill.handle(intent("WhatsPlayingIntent"))
    assert "Song 1 by Artist 1" in resp["response"]["outputSpeech"]["ssml"]


async def test_shuffle_keeps_current_song_and_clears_enqueued(skill: Skill) -> None:
    await start(skill)
    resp = await skill.handle(intent("AMAZON.ShuffleOnIntent"))
    assert directives(resp)[0]["type"] == "AudioPlayer.ClearQueue"
    state = skill.store.get(DEVICE)
    assert state.shuffle and state.tracks[0].video_id == "vid00000001"


async def test_speech_is_ssml_safe(skill: Skill) -> None:
    resp = await start(skill, "nothing <audio src='x'/> & more")
    ssml = resp["response"]["outputSpeech"]["ssml"]
    assert "<audio" not in ssml and "&" not in ssml.removeprefix("<speak>")


# --- signed-in library -------------------------------------------------------------------------
async def test_library_intents_ask_to_sign_in_first(skill: Skill) -> None:
    for name in ("PlayLikedIntent", "PlayMixIntent", "LikeIntent"):
        resp = await skill.handle(intent(name))
        if name == "LikeIntent":
            await start(skill)
            resp = await skill.handle(intent(name))
        assert "sign in" in resp["response"]["outputSpeech"]["ssml"]


async def test_play_liked_songs_playlist_and_mix(skill: Skill) -> None:
    skill.catalog.signed_in = True  # type: ignore[misc]
    resp = await skill.handle(intent("PlayLikedIntent"))
    assert "Playing your liked songs" in resp["response"]["outputSpeech"]["ssml"]
    assert len(skill.store.get(DEVICE).tracks) == 20

    resp = await skill.handle(_with_slot("PlayPlaylistIntent", "playlist", "road trip"))
    assert "Playing Road Trip" in resp["response"]["outputSpeech"]["ssml"]
    assert directives(resp)[0]["audioItem"]["metadata"]["title"] == "Song 600"

    resp = await skill.handle(_with_slot("PlayPlaylistIntent", "playlist", "gym"))
    assert "couldn't find a playlist called gym" in resp["response"]["outputSpeech"]["ssml"]

    resp = await skill.handle(_with_slot("PlayMixIntent", "mix", "supermix"))
    assert "My Supermix" in resp["response"]["outputSpeech"]["ssml"]


async def test_like_current_song_and_history(skill: Skill) -> None:
    skill.catalog.signed_in = True  # type: ignore[misc]
    resp = await start(skill)
    token = directives(resp)[0]["audioItem"]["stream"]["token"]
    resp = await skill.handle(intent("LikeIntent"))
    assert "Added Song 1 to your liked songs" in resp["response"]["outputSpeech"]["ssml"]
    assert list(skill.catalog.liked) == ["vid00000001"]  # type: ignore[attr-defined]
    await skill.handle(event("AudioPlayer.PlaybackStarted", token))
    await asyncio.sleep(0)  # history is reported in the background
    assert list(skill.catalog.history) == ["vid00000001"]  # type: ignore[attr-defined]


def _with_slot(name: str, slot: str, value: str) -> dict:  # type: ignore[type-arg]
    env = intent(name)
    env["request"]["intent"]["slots"] = {slot: {"name": slot, "value": value}}
    return env


async def test_shuffle_keeps_the_music_going(skill: Skill) -> None:
    """Review finding: shuffling made the playing song's token stale, so nothing got queued."""
    resp = await start(skill)
    token = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", token))
    await skill.handle(intent("AMAZON.ShuffleOnIntent"))
    resp = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", token))
    assert directives(resp), "the next song must still be queued after shuffling"
    assert directives(resp)[0]["playBehavior"] == "ENQUEUE"
    # and the playing song's own events still count
    await skill.handle(event("AudioPlayer.PlaybackStopped", token, offsetInMilliseconds=5_000))
    assert skill.store.get(DEVICE).offset_ms == 5_000


async def test_trimming_a_long_queue_keeps_tokens_valid(skill: Skill) -> None:
    from echo_tunes.player.state import PlayerState

    s = PlayerState()
    s.replace([song(i) for i in range(10)], max_len=12)
    s.index = 8
    token = s.token(8)
    s.extend([song(i) for i in range(10, 20)], max_len=12)  # drops played songs from the front
    assert s.index_from_token(token) == s.index


async def test_resume_does_not_count_twice(skill: Skill) -> None:
    from echo_tunes.history import History

    skill.history = History(":memory:", 15)
    resp = await start(skill)
    tok = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", tok, offsetInMilliseconds=0))
    await skill.handle(event("AudioPlayer.PlaybackStopped", tok, offsetInMilliseconds=40_000))
    await skill.handle(event("AudioPlayer.PlaybackStarted", tok, offsetInMilliseconds=40_000))
    await skill.wait_background()
    assert skill.history.count() == 1
    assert list(skill.catalog.history) == ["vid00000001"]  # reported to YouTube once  # type: ignore[attr-defined]


async def test_unknown_mix_says_so(skill: Skill) -> None:
    from echo_tunes.music.catalog import YTMusicCatalog

    class Home:
        def get_home(self, limit: int = 6) -> list:  # type: ignore[type-arg]
            return [{"contents": [{"title": "My Supermix", "playlistId": "RDTMAK5uy_x"}]}]

        def get_watch_playlist(self, **kw: object) -> dict:  # type: ignore[type-arg]
            return {"tracks": []}

    cat = YTMusicCatalog(Home(), signed_in=True)
    assert await cat.mix("jazz mix") is None
    found = await cat.mix("supermix")
    assert found is not None and found.title == "My Supermix"
