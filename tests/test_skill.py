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
    resp = await start(skill)
    await skill.handle(
        event("AudioPlayer.PlaybackStarted", directives(resp)[0]["audioItem"]["stream"]["token"])
    )
    resp = await skill.handle(intent("AMAZON.NextIntent"))
    assert skill.store.get(DEVICE).index == 1
    assert directives(resp)[0]["playBehavior"] == "REPLACE_ALL"
    await skill.handle(
        event("AudioPlayer.PlaybackStarted", directives(resp)[0]["audioItem"]["stream"]["token"])
    )
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


async def test_shuffle_keeps_current_song_and_replaces_enqueued(skill: Skill) -> None:
    resp = await start(skill)
    tok = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", tok))
    await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", tok))
    resp = await skill.handle(intent("AMAZON.ShuffleOnIntent"))
    [play] = directives(resp)
    assert play["type"] == "AudioPlayer.Play" and play["playBehavior"] == "REPLACE_ENQUEUED"
    assert "expectedPreviousToken" not in play["audioItem"]["stream"]
    state = skill.store.get(DEVICE)
    assert state.shuffle and state.tracks[0].video_id == "vid00000001"
    assert play["audioItem"]["metadata"]["title"] == state.tracks[1].title


async def test_mode_change_before_nearly_finished_queues_nothing_twice(skill: Skill) -> None:
    """Audit: "shuffle" or "loop" said before PlaybackNearlyFinished sent REPLACE_ENQUEUED with
    nothing queued, then NearlyFinished ENQUEUEd another song: two songs lined up."""
    for mode in ("AMAZON.ShuffleOnIntent", "AMAZON.LoopOnIntent", "AMAZON.ShuffleOffIntent"):
        resp = await start(skill)
        tok = directives(resp)[0]["audioItem"]["stream"]["token"]
        await skill.handle(event("AudioPlayer.PlaybackStarted", tok))
        resp = await skill.handle(intent(mode))
        assert not [d for d in directives(resp) if d["type"].startswith("AudioPlayer.")], mode
        nearly = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", tok))
        [enq] = directives(nearly)
        state = skill.store.get(DEVICE)
        assert enq["playBehavior"] == "ENQUEUE"
        assert enq["audioItem"]["metadata"]["title"] == state.tracks[state.index + 1].title


async def test_loop_off_on_the_last_song_carries_on_with_radio(skill: Skill) -> None:
    """Audit: "loop off" on the last song cleared the queued song instead of adding radio."""
    skill.catalog.signed_in = True  # type: ignore[misc]
    resp = await skill.handle(_with_slot("PlayPlaylistIntent", "playlist", "road trip"))
    await skill.handle(intent("AMAZON.LoopOnIntent"))
    state = skill.store.get(DEVICE)
    last = state.token(len(state.tracks) - 1)
    skill.store.put(DEVICE, state)
    await skill.handle(event("AudioPlayer.PlaybackStarted", last))
    nearly = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", last))
    assert directives(nearly)[0]["audioItem"]["metadata"]["title"] == "Song 600"  # loops round
    resp = await skill.handle(intent("AMAZON.LoopOffIntent"))
    [play] = [d for d in directives(resp) if d["type"] == "AudioPlayer.Play"]
    assert play["playBehavior"] == "REPLACE_ENQUEUED"
    assert play["audioItem"]["metadata"]["title"] not in {f"Song {i}" for i in range(600, 610)}
    assert len(skill.store.get(DEVICE).tracks) > 10  # radio was added


async def test_radio_is_shuffled_in_when_shuffle_is_on(skill: Skill, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Audit: with shuffle on, a voice-started radio still played in YouTube's order."""
    import random

    await start(skill)
    tok = skill.store.get(DEVICE).token(0)
    await skill.handle(intent("AMAZON.ShuffleOnIntent"))
    random.seed(1)
    resp = await start(skill, "something else")
    state = skill.store.get(DEVICE)
    radio = [t.video_id for t in state.tracks]
    assert state.shuffle and state.current is not None
    assert radio[0] == "vid00000001" and radio[1:] != sorted(radio[1:]), "radio order kept"
    assert sorted(state.unshuffled) == sorted(radio)
    await skill.handle(intent("AMAZON.ShuffleOffIntent"))
    assert [t.video_id for t in skill.store.get(DEVICE).tracks] == sorted(radio)
    assert tok and resp


async def test_mode_change_after_nearly_finished_keeps_music_going(skill: Skill) -> None:
    """Review finding: the Echo sends PlaybackNearlyFinished once per song, usually *before* the
    user says "shuffle"/"loop". The answer must queue a song, not just clear the queued one."""
    for mode in ("AMAZON.ShuffleOnIntent", "AMAZON.LoopOnIntent", "AMAZON.LoopOffIntent"):
        resp = await start(skill)
        tok = directives(resp)[0]["audioItem"]["stream"]["token"]
        await skill.handle(event("AudioPlayer.PlaybackStarted", tok))
        nearly = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", tok))
        assert directives(nearly)[0]["playBehavior"] == "ENQUEUE"
        resp = await skill.handle(intent(mode))
        plays = [d for d in directives(resp) if d["type"] == "AudioPlayer.Play"]
        assert plays and plays[0]["playBehavior"] == "REPLACE_ENQUEUED", mode


async def test_loop_with_one_song_uses_a_new_token(skill: Skill) -> None:
    skill.catalog.radio = _no_radio  # type: ignore[method-assign]
    resp = await start(skill)
    tok = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", tok))
    await skill.handle(intent("AMAZON.LoopOnIntent"))
    resp = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", tok))
    [play] = directives(resp)
    assert play["audioItem"]["stream"]["token"] != tok
    assert play["audioItem"]["stream"]["expectedPreviousToken"] == tok


async def _no_radio(video_id: str, limit: int) -> list:  # type: ignore[type-arg]
    return []


async def test_shuffle_off_restores_the_order(skill: Skill) -> None:
    await start(skill)
    before = [t.video_id for t in skill.store.get(DEVICE).tracks]
    await skill.handle(intent("AMAZON.ShuffleOnIntent"))
    await skill.handle(intent("AMAZON.ShuffleOffIntent"))
    assert [t.video_id for t in skill.store.get(DEVICE).tracks] == before


async def test_failed_queued_song_keeps_the_echo_shown_as_playing(skill: Skill) -> None:
    """Audit: a queued song failing marked the Echo as stopped while it still played."""
    resp = await start(skill)
    tok = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", tok))
    nearly = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", tok))
    queued = directives(nearly)[0]["audioItem"]["stream"]["token"]
    await skill.handle(
        event(
            "AudioPlayer.PlaybackFailed",
            queued,
            error={"type": "MEDIA_ERROR_UNKNOWN"},
            currentPlaybackState={"token": tok, "playerActivity": "PLAYING"},
        )
    )
    assert skill.store.get(DEVICE).playing is True


async def test_failed_enqueued_song_does_not_cut_off_the_playing_one(skill: Skill) -> None:
    resp = await start(skill)
    tok = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", tok))
    nearly = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", tok))
    queued = directives(nearly)[0]["audioItem"]["stream"]["token"]
    resp = await skill.handle(
        event(
            "AudioPlayer.PlaybackFailed",
            queued,
            error={"type": "MEDIA_ERROR_UNKNOWN"},
            currentPlaybackState={"token": tok, "playerActivity": "PLAYING"},
        )
    )
    [play] = directives(resp)
    assert play["playBehavior"] == "REPLACE_ENQUEUED"
    assert play["audioItem"]["metadata"]["title"] != "Song 1"
    assert skill.store.get(DEVICE).index == 0  # still on the playing song


async def test_failed_last_song_tops_up_the_queue(skill: Skill) -> None:
    resp = await start(skill)
    state = skill.store.get(DEVICE)
    last = len(state.tracks) - 1
    token = state.token(last)
    skill.store.put(DEVICE, state)
    resp = await skill.handle(
        event("AudioPlayer.PlaybackFailed", token, error={"type": "MEDIA_ERROR_UNKNOWN"})
    )
    assert directives(resp), "the radio should be extended and the next song played"


async def test_resume_after_the_song_ended_plays_the_next(skill: Skill) -> None:
    resp = await start(skill)
    tok = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", tok))
    await skill.handle(event("AudioPlayer.PlaybackFinished", tok, offsetInMilliseconds=200_000))
    env = intent("AMAZON.ResumeIntent")
    env["context"]["AudioPlayer"] = {"token": tok, "offsetInMilliseconds": 200_000}
    [play] = directives(await skill.handle(env))
    assert play["audioItem"]["stream"]["offsetInMilliseconds"] == 0
    assert play["audioItem"]["metadata"]["title"] != "Song 1"


async def test_slow_playlist_lookup_answers_within_alexas_limit(skill: Skill, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Audit: finding a playlist and loading it are two calls of up to 5 s each, past Alexa's
    ~8 s. The whole lookup has one budget and says sorry when it runs out."""
    import time

    from echo_tunes.alexa import skill as skill_module

    monkeypatch.setattr(skill_module, "COLLECTION_BUDGET", 0.2)
    skill.catalog.signed_in = True  # type: ignore[misc]

    async def slow(name: str) -> None:
        await asyncio.sleep(0.15)
        await asyncio.sleep(0.15)

    skill.catalog.playlist = slow  # type: ignore[method-assign]
    t0 = time.monotonic()
    resp = await skill.handle(_with_slot("PlayPlaylistIntent", "playlist", "road trip"))
    assert time.monotonic() - t0 < 0.29
    assert "slow right now" in resp["response"]["outputSpeech"]["ssml"]
    assert not directives(resp)


async def test_mix_synonym_uses_the_resolved_value(skill: Skill) -> None:
    skill.catalog.signed_in = True  # type: ignore[misc]
    asked: list[str] = []
    orig = skill.catalog.mix

    async def mix(name: str):  # type: ignore[no-untyped-def]
        asked.append(name)
        return await orig(name)

    skill.catalog.mix = mix  # type: ignore[method-assign]
    env = intent("PlayMixIntent")
    env["request"]["intent"]["slots"] = {
        "mix": {
            "name": "mix",
            "value": "second mix",
            "resolutions": {
                "resolutionsPerAuthority": [
                    {
                        "status": {"code": "ER_SUCCESS_MATCH"},
                        "values": [{"value": {"name": "mix 2"}}],
                    }
                ]
            },
        }
    }
    await skill.handle(env)
    assert asked == ["mix 2"]


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


async def test_answering_with_just_the_song_name_plays_it(skill: Skill) -> None:
    """Owner report: "Alexa, open my tunes" → "What would you like to play?" → "one love by
    blue" said "Sorry, I didn't get that": a bare song name matched no intent."""
    from .conftest import envelope

    launch = await skill.handle(envelope({"type": "LaunchRequest"}))
    assert launch["response"]["shouldEndSession"] is False
    env = intent("SongNameIntent")
    env["request"]["intent"]["slots"] = {"song": {"name": "song", "value": "one love by blue"}}
    resp = await skill.handle(env)
    await skill.wait_background()
    assert "Playing Song 1" in resp["response"]["outputSpeech"]["ssml"]
    assert directives(resp)[0]["playBehavior"] == "REPLACE_ALL"
    assert list(skill.catalog.searches)[-1] == "one love by blue"  # type: ignore[attr-defined]


# --- all of YouTube ----------------------------------------------------------------------------
async def test_youtube_intent_searches_youtube_not_youtube_music(skill: Skill) -> None:
    resp = await skill.handle(intent("PlayYouTubeIntent", "how to tie a tie"))
    await skill.wait_background()
    [play] = directives(resp)
    assert play["playBehavior"] == "REPLACE_ALL"
    assert "ytvid000001" in play["audioItem"]["stream"]["token"]
    assert "Playing A video by A channel from YouTube" in resp["response"]["outputSpeech"]["ssml"]
    assert list(skill.catalog.video_searches) == ["how to tie a tie"]  # type: ignore[attr-defined]
    assert not skill.catalog.searches  # type: ignore[attr-defined]
    state = skill.store.get(DEVICE)
    assert state.source == 'On YouTube: "how to tie a tie"'
    assert len(state.tracks) > 1  # radio follows, as for any song


async def test_on_youtube_said_to_the_play_intent_still_searches_youtube(skill: Skill) -> None:
    # Alexa's catch-all slot often takes the whole phrase: "play {kesariya on youtube}".
    for said in ("kesariya on youtube", "kesariya from You Tube", "kesariya off the youtube"):
        await skill.handle(intent("PlayIntent", said))
        await skill.wait_background()
    assert list(skill.catalog.video_searches) == ["kesariya"] * 3  # type: ignore[attr-defined]
    assert not skill.catalog.searches  # type: ignore[attr-defined]


async def test_youtube_in_a_song_name_is_left_alone(skill: Skill) -> None:
    await start(skill, "youtube rewind song")
    assert list(skill.catalog.searches) == ["youtube rewind song"]  # type: ignore[attr-defined]
    assert not skill.catalog.video_searches  # type: ignore[attr-defined]


async def test_only_on_youtube_asks_what_to_play(skill: Skill) -> None:
    resp = await skill.handle(intent("PlayYouTubeIntent", "on youtube"))
    assert resp["response"]["shouldEndSession"] is False
    assert not directives(resp)


async def test_youtube_not_found_and_unreachable(skill: Skill) -> None:
    resp = await skill.handle(intent("PlayYouTubeIntent", "nothing like this"))
    assert "couldn't find nothing like this on YouTube" in resp["response"]["outputSpeech"]["ssml"]
    skill.catalog.failing = {"search_video"}  # type: ignore[attr-defined]
    resp = await skill.handle(intent("PlayYouTubeIntent", "anything"))
    assert "couldn't reach YouTube." in resp["response"]["outputSpeech"]["ssml"]
    assert not directives(resp)
