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
_EXPORT = {
    "id": "export",
    "type": "export.nle",
    "needs": ["timeline"],
    "params": {"targets": ["resolve", "premiere", "kdenlive"]},
}
_EXPORT_WITH_SHORTS = {
    **_EXPORT,
    "needs": ["timeline", "render_shorts"],
}

BUILTIN_RECIPES: dict[str, dict[str, Any]] = {
    "youtube_talking_head": {
        "schema_version": 1,
        "id": "youtube_talking_head",
        "name": "YouTube talking head",
        "description": (
            "Clean speech, remove repeats, build the main timeline, and export an NLE project."
        ),
        "llm": {"provider": "none"},
        "steps": [_INGEST, _VAD, _TRANSCRIBE, _RETAKES, _TIMELINE, _EXPORT],
    },
    "viral_shorts_batch": {
        "schema_version": 1,
        "id": "viral_shorts_batch",
        "name": "Viral Shorts batch",
        "description": "Main timeline plus three vertical Shorts with burned captions.",
        "llm": {"provider": "none"},
        "steps": [
            _INGEST,
            _VAD,
            _TRANSCRIBE,
            {
                "id": "translation",
                "type": "transcript.translate",
                "needs": ["transcribe"],
                "params": {"target_language": "en"},
            },
            _RETAKES,
            _TIMELINE,
            {
                "id": "shorts",
                "type": "shorts.select",
                "needs": ["transcribe", "retakes"],
                "params": {
                    "target_duration_min_sec": 30,
                    "target_duration_max_sec": 60,
                    "min_clips": 1,
                    "max_clips_to_generate": 3,
                    "selection_mode": "auto",
                    "burn_subtitles": True,
                },
            },
            {
                "id": "reframe",
                "type": "shorts.reframe",
                "needs": ["shorts"],
                "params": {"mode": "center_crop_9_16"},
            },
            {
                "id": "captions",
                "type": "shorts.captions",
                "needs": ["shorts"],
                "params": {"enabled": True},
            },
            {
                "id": "render_shorts",
                "type": "shorts.render",
                "needs": ["reframe", "captions"],
                "params": {"burn_subtitles": True},
            },
            _EXPORT_WITH_SHORTS,
        ],
    },
    "content_cycle": {
        "schema_version": 1,
        "id": "content_cycle",
        "name": "Content cycle",
        "description": (
            "Full content lifecycle: idea, research, script, storyboard, production, "
            "audio, Shorts, titles, thumbnail, publishing, analytics, and review. "
            "Planned nodes are bypassed until implemented."
        ),
        "llm": {"provider": "none"},
        "steps": [
            {"id": "idea", "type": "content.idea", "params": {}},
            {"id": "research", "type": "content.research", "needs": ["idea"], "params": {}},
            {"id": "script", "type": "content.script", "needs": ["research"], "params": {}},
            _INGEST,
            _VAD,
            _TRANSCRIBE,
            _RETAKES,
            _TIMELINE,
            {
                "id": "storyboard",
                "type": "storyboard.plan",
                "needs": ["script", "timeline"],
                "params": {},
            },
            {
                "id": "assets",
                "type": "assets.index",
                "needs": ["ingest"],
                "params": {"asset_dir": ""},
            },
            {
                "id": "shorts",
                "type": "shorts.select",
                "needs": ["transcribe", "retakes"],
                "params": {
                    "target_duration_min_sec": 30,
                    "target_duration_max_sec": 60,
                    "min_clips": 1,
                    "max_clips_to_generate": 3,
                    "selection_mode": "auto",
                },
            },
            {
                "id": "reframe",
                "type": "shorts.reframe",
                "needs": ["shorts"],
                "params": {"mode": "center_crop_9_16"},
            },
            {
                "id": "captions",
                "type": "shorts.captions",
                "needs": ["shorts"],
                "params": {"enabled": True},
            },
            {
                "id": "render_shorts",
                "type": "shorts.render",
                "needs": ["reframe", "captions"],
                "params": {"burn_subtitles": True},
            },
            {
                "id": "color",
                "type": "color.grade",
                "needs": ["timeline"],
                "params": {},
            },
            {
                "id": "audio_master",
                "type": "audio.master",
                "needs": ["timeline"],
                "params": {},
            },
            {
                "id": "audio_qa",
                "type": "audio.qa",
                "needs": ["audio_master"],
                "params": {},
            },
            {
                "id": "titles",
                "type": "titles.plan",
                "needs": ["timeline"],
                "params": {},
            },
            {
                "id": "thumbnail",
                "type": "thumbnail.generate",
                "needs": ["render_shorts"],
                "params": {},
            },
            {
                "id": "publish",
                "type": "publish.webhook",
                "needs": ["render_shorts", "thumbnail"],
                "params": {},
            },
            {
                "id": "analytics",
                "type": "analytics.import",
                "needs": ["publish"],
                "params": {},
            },
            {
                "id": "review",
                "type": "review.queue",
                "needs": ["titles", "thumbnail"],
                "params": {},
            },
            _EXPORT_WITH_SHORTS,
        ],
    },
    "full_podcast_curation": {
        "schema_version": 1,
        "id": "full_podcast_curation",
        "name": "Full podcast curation",
        "description": (
            "Long-form cut, NLE exports, and five Shorts with audio-energy and scene boosts."
        ),
        "llm": {"provider": "none"},
        "steps": [
            _INGEST,
            _VAD,
            _TRANSCRIBE,
            _RETAKES,
            _TIMELINE,
            {
                "id": "shorts",
                "type": "shorts.select",
                "needs": ["transcribe", "retakes"],
                "params": {
                    "target_duration_min_sec": 25,
                    "target_duration_max_sec": 55,
                    "min_clips": 1,
                    "max_clips_to_generate": 5,
                    "selection_mode": "auto",
                    "audio_energy_boost": True,
                    "scene_change_boost": True,
                    "burn_subtitles": True,
                },
            },
            {
                "id": "reframe",
                "type": "shorts.reframe",
                "needs": ["shorts"],
                "params": {"mode": "center_crop_9_16"},
            },
            {
                "id": "captions",
                "type": "shorts.captions",
                "needs": ["shorts"],
                "params": {"enabled": True},
            },
            {
                "id": "render_shorts",
                "type": "shorts.render",
                "needs": ["reframe", "captions"],
                "params": {"burn_subtitles": True},
            },
            _EXPORT_WITH_SHORTS,
        ],
    },
}


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


def restore_recipe_version(recipe_id: str, version: str) -> Recipe:
    path = recipe_history_dir(recipe_id) / f"{version}.json"
    if not path.is_file():
        raise RecipeError(f"Unknown recipe version: {version}")
    recipe = load_recipe(path)
    save_user_recipe(recipe)
    return recipe
