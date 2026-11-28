# Voice commands

Start every request with **"Alexa, ask my tunes to …"** (or open the skill with
*"Alexa, open my tunes"* and then say what you'd like). While music is playing, the playback
commands work on their own: *"Alexa, next"*.

## Play something

| Say                                                  | What happens                                                |
| ---------------------------------------------------- | ----------------------------------------------------------- |
| "… play **Blinding Lights**"                         | Plays the best match, then a radio of similar songs.        |
| "… play **songs by Arijit Singh**"                   | Plays a top song by the artist, then similar songs.         |
| "… play **radio for Tum Hi Ho**"                     | Same as play, but tells you it's starting a radio.          |
| "… play **something like Coldplay**"                 | Radio based on the best match.                              |

## Anything on YouTube

Add **"on YouTube"** to search all of YouTube instead of just YouTube Music: covers, live sets,
fan cams, talks, podcasts.

| Say                                                  | What happens                                                |
| ---------------------------------------------------- | ----------------------------------------------------------- |
| "… play **Kesariya unplugged on YouTube**"           | Plays the top YouTube result, then a radio of similar songs. |
| "… **search YouTube for** lofi study session"        | The same.                                                    |
| "… play **the YouTube video** how to tie a tie"      | The same.                                                    |

Alexa says a short title ("Playing Kesariya - Film Version by SonyMusicIndia from YouTube"):
the first part of the video's title (before " | "), without filler like "(Official Video)" or
emoji. The web player shows the full title.

Keep "ask my tunes" in the sentence: *"Alexa, play … on YouTube"* on its own goes to Alexa's
built-in music services, not to echo-tunes. Live streams are skipped (the Echo can't play
them). The radio after a video comes from YouTube Music, so it suits music better than talks.

Or in two steps: say **"Alexa, open my tunes"**, and when it asks *"What would you like to play?"*,
just say the song: **"One Love by Blue"** (no need to say "play").

The queue never runs dry: when it's nearly finished, more songs are added from a radio based on
the current song. Searches use your `ECHO_TUNES_LOCATION` country for better local results.

## Your own music (after [signing in](GOOGLE_SIGN_IN.md))

| Say                                          | What happens                                          |
| -------------------------------------------- | ----------------------------------------------------- |
| "… play **my liked songs**" / "**my likes**" | Your liked songs, newest first                        |
| "… play **my playlist Road Trip**"           | A playlist from your library (close names are fine)   |
| "… play **my supermix**"                     | Your My Supermix                                      |
| "… play **my discover mix**" / "**my replay mix**" / "**my mix 1**" | That mix from your home page |
| "… **like this song**"                       | Adds the playing song to your liked songs             |

Say *"Alexa, shuffle"* after starting a playlist to shuffle it. When a playlist ends, a radio
based on its last song carries on.

## While music is playing

| Say                                   | Also on buttons / Alexa app | What happens                                   |
| ------------------------------------- | --------------------------- | ---------------------------------------------- |
| "Alexa, **next**" / "**skip**"        | ⏭                           | Next song                                       |
| "Alexa, **previous**" / "**go back**" | ⏮                           | Previous song                                   |
| "Alexa, **pause**" / "**stop**"       | ⏸                           | Pauses (remembers the position)                 |
| "Alexa, **resume**"                   | ▶                           | Continues where it paused                       |
| "Alexa, **start over**" / "**repeat**" |                            | Restarts the current song                       |
| "Alexa, **shuffle**" / "**stop shuffling**" |                       | Shuffles the songs after the current one        |
| "Alexa, **loop**" / "**stop looping**" |                            | Repeats the whole queue instead of adding radio |
| "Alexa, ask my tunes **what's playing**" |                        | Says the song and artist (a short title)        |

## Tips

- **Name it the way it appears on YouTube Music.** "Play Shape of You Ed Sheeran" is more
  reliable than "play that Ed Sheeran song".
- **Shorter phrase:** in the Alexa app, create a routine with a custom phrase such as
  *"Alexa, Bollywood time"* whose action is *Custom → "ask my tunes to play Bollywood hits"*.
- **Volume** works as usual ("Alexa, volume 5"); it doesn't go through echo-tunes.
