"""The Alexa skill definition must stay consistent with the code that handles it."""

from __future__ import annotations

import json
import re
from pathlib import Path

PKG = Path(__file__).parent.parent / "skill-package"
MODELS = sorted((PKG / "interactionModels/custom").glob("*.json"))
SKILL_SRC = (Path(__file__).parent.parent / "src/echo_tunes/alexa/skill.py").read_text()

# Amazon requires these for skills that use the AudioPlayer interface.
AUDIO_PLAYER_REQUIRED = {
    "AMAZON.PauseIntent",
    "AMAZON.ResumeIntent",
    "AMAZON.CancelIntent",
    "AMAZON.StopIntent",
    "AMAZON.HelpIntent",
    "AMAZON.NextIntent",
    "AMAZON.PreviousIntent",
    "AMAZON.StartOverIntent",
    "AMAZON.RepeatIntent",
    "AMAZON.ShuffleOnIntent",
    "AMAZON.ShuffleOffIntent",
    "AMAZON.LoopOnIntent",
    "AMAZON.LoopOffIntent",
}


def intents(path: Path) -> dict[str, dict]:  # type: ignore[type-arg]
    lm = json.loads(path.read_text())["interactionModel"]["languageModel"]
    return {i["name"]: i for i in lm["intents"]}


def test_all_locales_identical() -> None:
    assert len(MODELS) >= 3
    first = MODELS[0].read_text()
    for m in MODELS[1:]:
        assert m.read_text() == first, f"{m.name} differs from {MODELS[0].name}"


def test_required_audio_player_intents_present() -> None:
    missing = AUDIO_PLAYER_REQUIRED - set(intents(MODELS[0]))
    assert not missing, f"Amazon requires these for AudioPlayer skills: {missing}"


def test_every_intent_is_handled_in_code() -> None:
    for name in intents(MODELS[0]):
        if name in {"AMAZON.NavigateHomeIntent"}:
            continue  # falls through to the default "end session" branch
        assert f'"{name}"' in SKILL_SRC, f"{name} is in the model but not handled in skill.py"


def test_samples_reference_defined_slots_and_are_unique() -> None:
    seen: set[str] = set()
    for intent in intents(MODELS[0]).values():
        slots = {s["name"] for s in intent.get("slots", [])}
        for sample in intent.get("samples", []):
            assert set(re.findall(r"{(\w+)}", sample)) <= slots, sample
            assert sample not in seen, f"duplicate sample {sample!r}"
            seen.add(sample)


def test_generated_files_are_up_to_date() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_voice_model", PKG.parent / "scripts/build_voice_model.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for path, text in mod.render().items():
        assert path.read_text() == text, (
            f"run: uv run python scripts/build_voice_model.py ({path.name})"
        )


def test_manifest_uses_audio_player_and_placeholder_endpoint() -> None:
    manifest = json.loads((PKG / "skill.json").read_text())["manifest"]
    assert {"type": "AUDIO_PLAYER"} in manifest["apis"]["custom"]["interfaces"]
    # the public repo must never ship someone's real address
    assert manifest["apis"]["custom"]["endpoint"]["uri"] == "https://YOUR-PUBLIC-URL/alexa"
