"""Build the Alexa voice model for every English locale from one definition.

Run after editing:  uv run python scripts/build_voice_model.py
Tests fail if the generated files are out of date.
"""

from __future__ import annotations

import json
from pathlib import Path

LOCALES = ["en-US", "en-GB", "en-IN", "en-CA", "en-AU"]
# What people say: "Alexa, ask my tunes to ...". It can't contain a wake word (Alexa, Amazon,
# Echo, Computer, Ziggy), which is why it isn't "echo tunes".
INVOCATION = "my tunes"
OUT = Path(__file__).resolve().parent.parent / "skill-package"

QUERY = [{"name": "query", "type": "AMAZON.SearchQuery"}]

INTENTS = [
    {
        "name": "PlayIntent",
        "slots": QUERY,
        "samples": [
            "play {query}",
            "play the song {query}",
            "play songs by {query}",
            "play music by {query}",
            "play some {query}",
            "put on {query}",
            "i want to hear {query}",
            "i want to listen to {query}",
            "listen to {query}",
            "can you play {query}",
            "start playing {query}",
        ],
    },
    {
        "name": "PlayRadioIntent",
        "slots": QUERY,
        "samples": [
            "play radio for {query}",
            "start radio for {query}",
            "start a radio for {query}",
            "play songs like {query}",
            "play music like {query}",
            "play something like {query}",
            "radio for {query}",
        ],
    },
    {
        # All of YouTube, not just YouTube Music: videos, covers, live sets, podcasts...
        "name": "PlayYouTubeIntent",
        "slots": QUERY,
        "samples": [
            "play {query} on youtube",
            "play {query} from youtube",
            "play {query} off youtube",
            "put on {query} from youtube",
            "play the youtube video {query}",
            "play the video {query}",
            "search youtube for {query}",
            "find {query} on youtube",
            "youtube {query}",
            "i want to hear {query} on youtube",
            "listen to {query} on youtube",
        ],
    },
    {
        "name": "PlayLikedIntent",
        "slots": [],
        "samples": [
            "play my liked songs",
            "play my likes",
            "play my liked music",
            "play songs i like",
            "play my favourites",
            "play my favorites",
            "play my favourite songs",
            "play my favorite songs",
            "play my music",
        ],
    },
    {
        "name": "PlayPlaylistIntent",
        "slots": [{"name": "playlist", "type": "AMAZON.SearchQuery"}],
        "samples": [
            "play my playlist {playlist}",
            "play the playlist {playlist}",
            "play playlist {playlist}",
            "play my {playlist} playlist",
        ],
    },
    {
        "name": "PlayMixIntent",
        "slots": [{"name": "mix", "type": "MixName"}],
        "samples": ["play my {mix}", "play {mix} for me", "start my {mix}", "play my mix"],
    },
    {
        # Answering "What would you like to play?" with just the song: "one love by blue".
        # AMAZON.SearchQuery can't stand alone in an utterance, so this uses a custom type
        # whose values are only examples: Alexa passes through whatever was said.
        "name": "SongNameIntent",
        "slots": [{"name": "song", "type": "SongName"}],
        "samples": ["{song}", "the song {song}", "how about {song}"],
    },
    {
        "name": "LikeIntent",
        "slots": [],
        "samples": [
            "like this song",
            "i like this song",
            "i love this song",
            "thumbs up",
            "add this to my liked songs",
            "save this song",
            "like this",
        ],
    },
    {
        "name": "WhatsPlayingIntent",
        "slots": [],
        "samples": [
            "what's playing",
            "what is playing",
            "what song is this",
            "what's this song",
            "who sings this",
            "what's the name of this song",
            "who is this",
            "what am i listening to",
        ],
    },
]

BUILT_INS = [
    "AMAZON.CancelIntent",
    "AMAZON.HelpIntent",
    "AMAZON.StopIntent",
    "AMAZON.NavigateHomeIntent",
    "AMAZON.FallbackIntent",
    "AMAZON.PauseIntent",
    "AMAZON.ResumeIntent",
    "AMAZON.NextIntent",
    "AMAZON.PreviousIntent",
    "AMAZON.StartOverIntent",
    "AMAZON.RepeatIntent",
    "AMAZON.ShuffleOnIntent",
    "AMAZON.ShuffleOffIntent",
    "AMAZON.LoopOnIntent",
    "AMAZON.LoopOffIntent",
]

# Examples only (any song name works): varied lengths, "title by artist", several languages.
SONG_EXAMPLES = [
    "one love by blue",
    "blinding lights",
    "shape of you by ed sheeran",
    "tum hi ho",
    "kesariya",
    "despacito",
    "bohemian rhapsody by queen",
    "perfect by ed sheeran",
    "hotel california by the eagles",
    "let it be",
    "imagine by john lennon",
    "hello by adele",
    "rolling in the deep",
    "someone like you",
    "billie jean by michael jackson",
    "thriller",
    "smells like teen spirit",
    "wonderwall by oasis",
    "yellow by coldplay",
    "fix you",
    "viva la vida",
    "lose yourself by eminem",
    "stay with me by sam smith",
    "believer",
    "thunder by imagine dragons",
    "levitating by dua lipa",
    "bad guy by billie eilish",
    "as it was by harry styles",
    "watermelon sugar",
    "dance monkey",
    "senorita",
    "channa mereya",
    "tujh mein rab dikhta hai",
    "kal ho naa ho",
    "chaiyya chaiyya",
    "jai ho by a r rahman",
    "agar tum saath ho",
    "raabta",
    "ae dil hai mushkil",
    "pehla nasha",
    "lag ja gale",
    "tere bina",
    "apna bana le",
    "pasoori",
    "naatu naatu",
    "srivalli",
    "butta bomma",
    "why this kolaveri di",
    "kun faya kun",
    "dil se re",
    "gangnam style",
    "dynamite by bts",
    "la vie en rose",
    "bella ciao",
    "hallelujah by leonard cohen",
    "nothing else matters by metallica",
    "numb by linkin park",
    "in the end",
    "counting stars",
    "see you again",
    "uptown funk",
    "happy by pharrell",
    "shallow by lady gaga",
    "all of me by john legend",
    "thinking out loud",
    "a thousand years",
    "photograph",
    "faded by alan walker",
    "closer by the chainsmokers",
]

TYPES = [
    {
        "name": "SongName",
        "values": [{"name": {"value": s}} for s in SONG_EXAMPLES],
    },
    {
        "name": "MixName",
        "values": [
            {"name": {"value": "supermix", "synonyms": ["super mix", "my supermix"]}},
            {"name": {"value": "discover mix", "synonyms": ["discovery mix", "discover"]}},
            {
                "name": {
                    "value": "new release mix",
                    "synonyms": ["new releases mix", "new music mix"],
                }
            },
            {"name": {"value": "replay mix", "synonyms": ["replay"]}},
            {"name": {"value": "mix 1", "synonyms": ["my mix 1", "first mix"]}},
            {"name": {"value": "mix 2", "synonyms": ["my mix 2", "second mix"]}},
            {"name": {"value": "mix 3", "synonyms": ["my mix 3", "third mix"]}},
        ],
    },
]

SUMMARY = "Play music from YouTube Music on your Echo, from your own server."
DESCRIPTION = (
    "A private, self-hosted skill. Say: Alexa, ask my tunes to play, followed by a song or "
    "artist. Sign in on your server to play your liked songs, playlists and mixes."
)
EXAMPLES = [
    "Alexa, ask my tunes to play Blinding Lights",
    "Alexa, ask my tunes to play my liked songs",
    "Alexa, ask my tunes what's playing",
]


def model() -> dict:  # type: ignore[type-arg]
    return {
        "interactionModel": {
            "languageModel": {
                "invocationName": INVOCATION,
                "intents": INTENTS + [{"name": n, "samples": []} for n in BUILT_INS],
                "types": TYPES,
            }
        }
    }


def manifest() -> dict:  # type: ignore[type-arg]
    return {
        "manifest": {
            "publishingInformation": {
                "locales": {
                    loc: {
                        "name": "echo tunes",
                        "summary": SUMMARY,
                        "description": DESCRIPTION,
                        "examplePhrases": EXAMPLES,
                        "keywords": ["music", "youtube music", "self-hosted"],
                    }
                    for loc in LOCALES
                },
                "isAvailableWorldwide": True,
                "testingInstructions": "Private self-hosted skill; not for certification.",
                "category": "MUSIC_AND_AUDIO",
                "distributionCountries": [],
            },
            "apis": {
                "custom": {
                    "endpoint": {
                        "uri": "https://YOUR-PUBLIC-URL/alexa",
                        "sslCertificateType": "Trusted",
                    },
                    "interfaces": [{"type": "AUDIO_PLAYER"}],
                }
            },
            "manifestVersion": "1.0",
            "privacyAndCompliance": {
                "allowsPurchases": False,
                "usesPersonalInfo": False,
                "isChildDirected": False,
                "isExportCompliant": True,
                "containsAds": False,
                "locales": {loc: {} for loc in LOCALES},
            },
        }
    }


def render() -> dict[Path, str]:
    files = {OUT / "skill.json": json.dumps(manifest(), indent=2) + "\n"}
    text = json.dumps(model(), indent=2) + "\n"
    for loc in LOCALES:
        files[OUT / "interactionModels" / "custom" / f"{loc}.json"] = text
    return files


if __name__ == "__main__":
    for path, text in render().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"wrote {path.relative_to(OUT.parent)}")
