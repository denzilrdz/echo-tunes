---
name: alexa-playback
description: Alexa AudioPlayer rules and how echo-tunes uses them. Use when changing src/echo_tunes/alexa/skill.py, player/state.py or responses.py, adding an intent or voice phrase, or when music stops, skips, repeats or plays the wrong song on an Echo.
---

# Alexa playback

echo-tunes is a custom skill with the AudioPlayer interface. Amazon reference:
<https://developer.amazon.com/docs/alexa/custom-skills/audioplayer-interface-reference.html>.

## What Alexa allows

- The skill can only act **in reply to a request from the Echo**. There's no way to push a
  directive (play, pause, skip) from the server on its own. Anything "remote control" must be
  applied in the reply to the next event (start, nearly finished, finished, failed).
- ~**8 s** to answer, including the search. Slow work (radio) runs after answering
  (`Skill._in_background`, `_fill_radio`), then takes the per-Echo lock and checks `state.rev`.
- **AudioPlayer._ and PlaybackController._ replies must not speak**: `r.only()` / `r.empty()`.
  PlaybackStopped replies can't carry directives at all.
- `PlaybackNearlyFinished` comes **once per song**, often soon after it starts (the Echo has
  buffered it). Whatever is queued then is what plays next.
- Play behaviors:
  - `REPLACE_ALL`: play now (voice "play", next/previous, a failed current song).
  - `ENQUEUE` + `expectedPreviousToken` = the playing token: in reply to NearlyFinished.
  - `REPLACE_ENQUEUED`: swap what's queued without touching what plays (shuffle, loop, a
    failed _queued_ song). No `expectedPreviousToken` with it.
- Two streams must never share a token: `PlayerState.token()` adds a play counter (loop with
  one song would otherwise ENQUEUE the playing token).

## Tokens and state (`player/state.py`)

- Token `rev:index:videoId:plays`. `rev` changes only when the queue is **replaced**; reorders
  and trims keep it, and `index_from_token` falls back to finding the song by ID.
- `finished` is set on PlaybackFinished of the current song: "resume" then plays the next song
  from 0 instead of the last second of the old one.
- `enqueued`: the song the Echo has lined up (set by every ENQUEUE/REPLACE_ENQUEUED in
  `Skill._play`, cleared on PlaybackStarted, REPLACE_ALL and `replace()`). Shuffle/loop send
  REPLACE_ENQUEUED only when something is enqueued; otherwise NearlyFinished picks the right
  song (sending one too would queue two).
- Shuffle keeps the original order in `unshuffled` (also for a one-song start, so radio added
  later is shuffled in); shuffle off restores it. Dashboard picks are added to `unshuffled`
  too. A new queue with shuffle on starts on a random song.
- `PlaybackFailed`: if `currentPlaybackState` shows another song still PLAYING, the failure
  was the queued song: `REPLACE_ENQUEUED` the one after it. Three failures in a row stop.

## Voice model

`scripts/build_voice_model.py` generates `skill-package/interactionModels/custom/*.json` for
every locale from one definition. Synonyms (e.g. "second mix" → `mix 2`) reach the skill as
entity resolutions: read them with `_slot(intent, name, resolved=True)`.

## Checklist for a playback change

1. Write the test first in `tests/test_skill.py`, in the order the Echo sends events
   (Play → PlaybackStarted → PlaybackNearlyFinished → the voice command → ...).
2. Check the reply type: speech only for IntentRequest; directives allowed for the event.
3. `uv run pytest -q tests/test_skill.py tests/test_queue_machine.py`.
4. Test on a real Echo: the developer console's simulator doesn't play audio.

## The web player and an Echo

The dashboard can't push to an Echo. `Skill.dashboard_queue()` edits the queue
(`PlayerState.insert`): *Next* goes after the song the Echo has already lined up (`enqueued`),
else right after the current one; *Add to queue* at the end; *Play* right after the current
one and sets `state.pending`. The next `PlaybackNearlyFinished` enqueues it naturally; if the
Echo had already lined up another song, the `PlaybackStarted` of that song is answered with a
`REPLACE_ALL` of the pending one (`_pending_jump`). Any REPLACE_ALL we send (a new queue, voice
next/previous/start over/resume) clears `pending`, so an old pick never hijacks a newer
command; resume plays a pick made while paused; a pick that fails is skipped, not retried. "Skip now" (experimental) cuts the playing
song's open streams (`StreamSlots.cut`) and refuses new ones for 30 s, so the Echo reports
`PlaybackFailed` and the reply plays the pending song.
