"""What the skill says and does when YouTube Music fails (the fakes raise on request)."""

from __future__ import annotations

from echo_tunes.alexa.skill import Skill

from .conftest import DEVICE, directives, event, intent


def _speech(resp: dict) -> str:  # type: ignore[type-arg]
    return str(resp["response"].get("outputSpeech", {}).get("ssml", ""))


async def test_search_failure_is_spoken_not_crashed(skill: Skill) -> None:
    skill.catalog.failing.add("search_song")  # type: ignore[attr-defined]
    resp = await skill.handle(intent("PlayIntent", "anything"))
    assert "couldn't reach YouTube Music" in _speech(resp) and not directives(resp)


async def test_radio_failure_still_plays_the_song(skill: Skill) -> None:
    skill.catalog.failing.add("radio")  # type: ignore[attr-defined]
    resp = await skill.handle(intent("PlayIntent", "tum hi ho"))
    await skill.wait_background()
    assert directives(resp)[0]["audioItem"]["metadata"]["title"] == "Song 1"
    assert len(skill.store.get(DEVICE).tracks) == 1


async def test_top_up_failure_at_queue_end_is_quiet(skill: Skill) -> None:
    skill.catalog.failing.add("radio")  # type: ignore[attr-defined]
    resp = await skill.handle(intent("PlayIntent", "tum hi ho"))
    tok = directives(resp)[0]["audioItem"]["stream"]["token"]
    resp = await skill.handle(event("AudioPlayer.PlaybackNearlyFinished", tok))
    assert resp["response"] == {}


async def test_library_failures_are_spoken(skill: Skill) -> None:
    skill.catalog.signed_in = True  # type: ignore[misc]
    for method, name in (("liked_songs", "PlayLikedIntent"), ("mix", "PlayMixIntent")):
        skill.catalog.failing.add(method)  # type: ignore[attr-defined]
        assert "couldn't reach YouTube Music" in _speech(await skill.handle(intent(name)))


async def test_like_failure_is_spoken(skill: Skill) -> None:
    skill.catalog.signed_in = True  # type: ignore[misc]
    await skill.handle(intent("PlayIntent", "tum hi ho"))
    skill.catalog.failing.add("like")  # type: ignore[attr-defined]
    assert "couldn't reach YouTube Music" in _speech(await skill.handle(intent("LikeIntent")))


async def test_hardware_buttons(skill: Skill) -> None:
    resp = await skill.handle(intent("PlayIntent", "tum hi ho"))
    await skill.wait_background()
    tok = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", tok))
    nxt = await skill.handle(event("PlaybackController.NextCommandIssued", tok))
    assert directives(nxt)[0]["playBehavior"] == "REPLACE_ALL"
    assert "outputSpeech" not in nxt["response"]  # buttons must not speak
    prev = await skill.handle(event("PlaybackController.PreviousCommandIssued", tok))
    assert directives(prev)[0]["audioItem"]["metadata"]["title"] == "Song 1"
    pause = await skill.handle(event("PlaybackController.PauseCommandIssued", tok))
    assert directives(pause)[0]["type"] == "AudioPlayer.Stop"
    play = await skill.handle(event("PlaybackController.PlayCommandIssued", tok))
    assert directives(play)[0]["type"] == "AudioPlayer.Play"


async def test_playback_finished_is_recorded(skill: Skill) -> None:
    from echo_tunes.history import History

    skill.history = History(":memory:", 15)
    resp = await skill.handle(intent("PlayIntent", "tum hi ho"))
    tok = directives(resp)[0]["audioItem"]["stream"]["token"]
    await skill.handle(event("AudioPlayer.PlaybackStarted", tok))
    await skill.handle(event("AudioPlayer.PlaybackFinished", tok, offsetInMilliseconds=200_000))
    [row] = skill.history.recent(limit=10)
    assert row["status"] == "finished"
