"""Built-in recipes and user-recipe discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoflow.core.recipe import RECIPE_ID, Recipe, load_recipe, parse_recipe
from videoflow.domain.errors import RecipeError
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
    "needs": ["transcribe"],
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
            _RETAKES,
            _TIMELINE,
            {
                "id": "shorts",
                "type": "shorts.select",
                "needs": ["transcribe"],
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
                "id": "render_shorts",
                "type": "shorts.render",
                "needs": ["shorts"],
                "params": {"burn_subtitles": True},
            },
            _EXPORT,
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
                "needs": ["transcribe"],
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
                "id": "render_shorts",
                "type": "shorts.render",
                "needs": ["shorts"],
                "params": {"burn_subtitles": True},
            },
            _EXPORT,
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


def get_recipe(recipe_id: str) -> Recipe:
    if not RECIPE_ID.match(recipe_id):
        raise RecipeError(f"Invalid recipe id: {recipe_id}")
    path = user_recipes_dir() / f"{recipe_id}.json"
    if path.is_file():
        return load_recipe(path)
    if recipe_id in BUILTIN_RECIPES:
        return builtin_recipe(recipe_id)
    raise RecipeError(f"Unknown recipe: {recipe_id}")


def save_user_recipe(recipe: Recipe) -> Path:
    directory = user_recipes_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{recipe.id}.json"
    path.write_text(json.dumps(recipe.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return path
