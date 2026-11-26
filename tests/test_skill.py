from __future__ import annotations

from echo_tunes import tokens
from echo_tunes.alexa.skill import Skill

from .conftest import DEVICE, SECRET, directives, envelope, event, intent


async def start(skill: Skill, query: str = "tum hi ho") -> dict:
    return await skill.handle(intent("PlayIntent", query))


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
