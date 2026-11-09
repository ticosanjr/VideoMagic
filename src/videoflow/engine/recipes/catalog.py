"""Built-in recipes and user-recipe discovery."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from videoflow.core.recipe import RECIPE_ID, Recipe, load_recipe, parse_recipe
from videoflow.domain.errors import RecipeError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import portable_home

_INGEST = {
    "id": "ingest",
    "type": "ingest",
    "params": {"extract_pcm": True},
}
_VAD = {
    "id": "vad",
    "type": "audio.vad",
    "needs": ["ingest"],
    "params": {},
}
_TRANSCRIBE = {
    "id": "transcribe",
    "type": "transcribe",
    "needs": ["ingest"],
    "params": {"mode": "auto", "language": "pt", "model_size": "small"},
}
_TRANSLATE = {
    "id": "translation",
    "type": "transcript.translate",
    "needs": ["transcribe"],
    "params": {"target_language": "en"},
}
_RETAKES = {
    "id": "retakes",
    "type": "retakes.cull",
    "needs": ["vad", "transcribe"],
    "params": {"enabled": True},
}
_TIMELINE = {
    "id": "timeline",
    "type": "edit.timeline",
    "needs": ["vad", "retakes"],
    "params": {},
}
_TIMELINE_NO_RETAKES = {**_TIMELINE, "needs": ["vad"]}
_EXPORT = {
    "id": "export",
    "type": "export.nle",
    "needs": ["timeline"],
    "params": {
        "targets": ["resolve", "premiere", "kdenlive"],
        "filename_mode": "source_timestamp",
    },
}
_EXPORT_WITH_SHORTS = {
    **_EXPORT,
    "needs": ["timeline", "render_shorts"],
}

BUILTIN_RECIPES: dict[str, dict[str, Any]] = {}

def _add_recipe(
    recipe_id: str,
    name: str,
    steps: list[dict[str, Any]],
    *,
    description: str = "",
    variables: dict[str, Any] | None = None,
    variants: list[dict[str, Any]] | None = None,
) -> None:
    BUILTIN_RECIPES[recipe_id] = {
        "schema_version": 1,
        "id": recipe_id,
        "name": name,
        "description": description or name,
        "llm": {"provider": "none"},
        "variables": variables or {},
        "variants": variants or [],
        "steps": steps,
    }


def _shorts(
    *,
    minimum: int = 30,
    maximum: int = 60,
    count: int = 3,
    profile: str = "default",
    top_k: int = 0,
    hook_mode: str = "off",
    selection_mode: str = "auto",
    aspect: str = "9:16",
    caption_size: int = 72,
) -> list[dict[str, Any]]:
    return [
        {**_INGEST},
        {**_VAD},
        {**_TRANSCRIBE},
        {**_RETAKES},
        {
            "id": "shorts",
            "type": "shorts.select",
            "needs": ["transcribe", "retakes"],
            "params": {
                "target_duration_min_sec": minimum,
                "target_duration_max_sec": maximum,
                "min_clips": 1,
                "max_clips_to_generate": count,
                "selection_mode": selection_mode,
                "hook_mode": hook_mode,
                "aspect_ratio": aspect,
                "audio_energy_boost": True,
                "scene_change_boost": True,
            },
        },
        {
            "id": "score",
            "type": "shorts.score",
            "needs": ["shorts"],
            "params": {"profile": profile, "top_k": top_k},
        },
        {
            "id": "reframe",
            "type": "shorts.reframe",
            "needs": ["score"],
            "params": {"mode": "center_crop_9_16"},
        },
        {
            "id": "captions",
            "type": "shorts.captions",
            "needs": ["score"],
            "params": {
                "enabled": True,
                "caption_style": {"font_size": caption_size},
            },
        },
        {
            "id": "render",
            "type": "shorts.render",
            "needs": ["reframe", "captions"],
            "params": {
                "burn_subtitles": True,
                "caption_style": {"font_size": caption_size},
            },
        },
    ]

def _localized_steps() -> list[dict[str, Any]]:
    """Viral Shorts followed by one dubbing step before the NLE export."""

    steps = [dict(step) for step in BUILTIN_RECIPES["viral_shorts_batch"]["steps"]]
    insert_at = next(
        (index for index, step in enumerate(steps) if step.get("type") == "export.nle"),
        len(steps),
    )
    steps.insert(
        insert_at,
        {
            "id": "dub",
            "type": "localization.dub",
            "needs": ["render_shorts"],
            "params": {"target_language": "en", "original_volume": 0.15},
        },
    )
    return steps

def _recut_steps(*, with_retakes: bool) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = [
        {"id": "ingest", "type": "ingest", "params": {"extract_pcm": True}},
        {
            "id": "vad",
            "type": "audio.vad",
            "needs": ["ingest"],
            "inputs": {"media": "ingest.media"},
            "params": {
                "engine": "auto",
                "noise_db": -30.0,
                "speech_threshold": 0.5,
                "min_silence_ms": 350,
                "min_speech_ms": 120,
                "spike_suppression_ms": 180,
                "merge_gap_ms": 120,
                "pad_before_ms": 80,
                "pad_after_ms": 120,
                "apply_pads": False,
            },
        },
    ]
    timeline_needs = ["vad"]
    if with_retakes:
        steps.append(
            {
                "id": "transcribe",
                "type": "transcribe",
                "needs": ["ingest"],
                "inputs": {"media": "ingest.media"},
                "params": {"mode": "auto", "language": "pt", "model_size": "small"},
            }
        )
        steps.append(
            {
                "id": "retakes",
                "type": "retakes.cull",
                "needs": ["vad", "transcribe"],
                "inputs": {
                    "speech": "vad.speech",
                    "transcript": "transcribe.transcript",
                },
                "params": {
                    "enabled": True,
                    "strategy": "keep_last",
                    "strictness": "balanced",
                },
            }
        )
        timeline_needs.append("retakes")
    steps.append(
        {
            "id": "timeline",
            "type": "edit.timeline",
            "needs": timeline_needs,
            "inputs": (
                {
                    "speech": "retakes.speech",
                    "transcript": "transcribe.transcript",
                    "silence": "vad.silence",
                    "retakes": "retakes.retakes",
                }
                if with_retakes
                else {"speech": "vad.speech", "silence": "vad.silence"}
            ),
            "params": {
                "cut_mode": "hard",
                "enable_j_cuts": False,
                "enable_l_cuts": False,
                "offset_ms": 200,
                "audio_crossfade_ms": 20,
                "fade_in_ms": 20,
                "fade_out_ms": 20,
                "handle_check": True,
                "transition_frames": 0,
                "transition_type": "crossfade",
                "zoom_mode": "manual_rules",
            },
        }
    )
    steps.append(
        {
            "id": "export",
            "type": "export.nle",
            "needs": ["timeline"],
            "inputs": {"timeline": "timeline.timeline"},
            "params": {
        "targets": ["resolve", "premiere", "kdenlive"],
        "filename_mode": "source_timestamp",
    },
        }
    )
    return steps

def _recut_preset(
    recipe_id: str,
    name: str,
    description: str,
    *,
    with_retakes: bool,
    vad: dict[str, object],
    timeline: dict[str, object],
) -> None:
    steps = _recut_steps(with_retakes=with_retakes)
    for step in steps:
        if step["id"] == "vad":
            step["params"] = {**step["params"], **vad}
        if step["id"] == "timeline":
            step["params"] = {**step["params"], **timeline}
    _add_recipe(recipe_id, name, steps, description=description)


_recut_preset(
    "recut_podcast",
    "Recut Podcast",
    "Two-speaker podcast recut with retakes, J-cuts, and generous handles.",
    with_retakes=True,
    vad={
        "noise_db": -34.0,
        "speech_threshold": 0.45,
        "min_silence_ms": 500,
        "min_speech_ms": 140,
        "spike_suppression_ms": 260,
        "merge_gap_ms": 180,
        "pad_before_ms": 120,
        "pad_after_ms": 180,
    },
    timeline={
        "cut_mode": "j_cut",
        "enable_j_cuts": True,
        "enable_l_cuts": False,
        "offset_ms": 220,
        "audio_crossfade_ms": 30,
    },
)
_recut_preset(
    "recut_lecture",
    "Recut Lecture",
    "Deterministic class or webinar recut with hard cuts and wide handles.",
    with_retakes=False,
    vad={
        "noise_db": -38.0,
        "speech_threshold": 0.4,
        "min_silence_ms": 650,
        "min_speech_ms": 160,
        "spike_suppression_ms": 300,
        "merge_gap_ms": 220,
        "pad_before_ms": 150,
        "pad_after_ms": 220,
    },
    timeline={"cut_mode": "hard", "offset_ms": 200, "audio_crossfade_ms": 20},
)
_recut_preset(
    "recut_social",
    "Recut Social",
    "Tight social recut with retakes, short handles, and L-cuts.",
    with_retakes=True,
    vad={
        "noise_db": -24.0,
        "speech_threshold": 0.62,
        "min_silence_ms": 240,
        "min_speech_ms": 90,
        "spike_suppression_ms": 120,
        "merge_gap_ms": 70,
        "pad_before_ms": 40,
        "pad_after_ms": 60,
    },
    timeline={
        "cut_mode": "l_cut",
        "enable_j_cuts": False,
        "enable_l_cuts": True,
        "offset_ms": 180,
        "audio_crossfade_ms": 15,
    },
)

def builtin_recipe(recipe_id: str) -> Recipe:
    try:
        payload = BUILTIN_RECIPES[recipe_id]
    except KeyError as exc:
        raise RecipeError(f"Unknown recipe: {recipe_id}") from exc
    return parse_recipe(payload)


def user_recipes_dir() -> Path:
    return portable_home() / "recipes"


def list_recipes() -> list[dict[str, object]]:
    recipes: list[dict[str, object]] = []
    seen: set[str] = set()
    directory = user_recipes_dir()
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            try:
                recipe = load_recipe(path)
            except RecipeError:
                continue
            if recipe.id in seen:
                continue
            recipes.append(
                {
                    "id": recipe.id,
                    "name": recipe.name,
                    "description": recipe.description,
                    "source": str(path),
                }
            )
            seen.add(recipe.id)
    for recipe_id, payload in BUILTIN_RECIPES.items():
        if recipe_id in seen:
            continue
        recipes.append(
            {
                "id": recipe_id,
                "name": payload["name"],
                "description": payload.get("description", ""),
                "source": "builtin",
            }
        )
        seen.add(recipe_id)
    return recipes


def resolve_recipe_paths(recipe: Recipe, roots: list[Path]) -> Recipe:
    """Resolve operator-supplied paths inside the allowlist before execution."""

    payload = recipe.model_dump(mode="json")
    for step in payload.get("steps", []):
        params = step.get("params")
        if not isinstance(params, dict):
            continue
        if step.get("type") == "transcribe" and params.get("srt_path"):
            params["srt_path"] = str(resolve_allowed(Path(str(params["srt_path"])), roots))
        if step.get("type") == "shorts.render":
            for key in (
                "overlay_path",
                "music_path",
                "intro_path",
                "outro_path",
                "second_source_path",
            ):
                if params.get(key):
                    params[key] = str(resolve_allowed(Path(str(params[key])), roots))
        if step.get("type") == "broll.plan" and params.get("asset_dir"):
            params["asset_dir"] = str(resolve_allowed(Path(str(params["asset_dir"])), roots))
    return parse_recipe(payload)


def get_recipe(recipe_id: str) -> Recipe:
    if not RECIPE_ID.match(recipe_id):
        raise RecipeError(f"Invalid recipe id: {recipe_id}")
    path = user_recipes_dir() / f"{recipe_id}.json"
    if path.is_file():
        return load_recipe(path)
    if recipe_id in BUILTIN_RECIPES:
        return builtin_recipe(recipe_id)
    raise RecipeError(f"Unknown recipe: {recipe_id}")


def recipe_history_dir(recipe_id: str) -> Path:
    return user_recipes_dir() / "history" / recipe_id


def save_user_recipe(recipe: Recipe) -> Path:
    directory = user_recipes_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{recipe.id}.json"
    if path.is_file():
        history = recipe_history_dir(recipe.id)
        history.mkdir(parents=True, exist_ok=True)
        stamp = time.time_ns()
        shutil.copy2(path, history / f"{stamp}.json")
        entries = sorted(history.glob("*.json"), key=lambda item: item.stem)
        for stale in entries[:-20]:
            stale.unlink(missing_ok=True)
    path.write_text(json.dumps(recipe.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return path


def list_recipe_history(recipe_id: str) -> list[dict[str, object]]:
    directory = recipe_history_dir(recipe_id)
    entries: list[dict[str, object]] = []
    if not directory.is_dir():
        return entries
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stem, reverse=True):
        try:
            recipe = load_recipe(path)
        except RecipeError:
            continue
        entries.append(
            {
                "version": path.stem,
                "name": recipe.name,
                "description": recipe.description,
                "step_count": len(recipe.steps),
            }
        )
    return entries


def get_recipe_version(recipe_id: str, version: str) -> Recipe:
    if not version.isdigit():
        raise RecipeError(f"Unknown recipe version: {version}")
    path = recipe_history_dir(recipe_id) / f"{version}.json"
    if not path.is_file():
        raise RecipeError(f"Unknown recipe version: {version}")
    return load_recipe(path)


def restore_recipe_version(recipe_id: str, version: str) -> Recipe:
    path = recipe_history_dir(recipe_id) / f"{version}.json"
    if not path.is_file():
        raise RecipeError(f"Unknown recipe version: {version}")
    recipe = load_recipe(path)
    save_user_recipe(recipe)
    return recipe
