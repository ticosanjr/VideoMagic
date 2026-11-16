"""Apply a channel kit and hard constraints to a recipe."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from videoflow.core.recipe import Recipe
from videoflow.domain.headless import PresetRulebook
from videoflow.steps.registry import get_step


def _merge_defaults(params: dict[str, Any], defaults: dict[str, Any]) -> None:
    for key, value in defaults.items():
        if key not in params or params[key] in {None, "", [], {}}:
            params[key] = deepcopy(value)


def apply_channel_kit(recipe: Recipe, book: PresetRulebook) -> Recipe:
    """Return a copy with kit defaults and inviolable hard constraints."""

    updated = recipe.model_copy(deep=True)
    kit = book.channel_kit
    hard = book.hard_constraints
    for step in updated.steps:
        params = step.params if isinstance(step.params, dict) else {}
        step.params = params
        try:
            allowed = set(get_step(step.type).params_model.model_fields)
        except Exception:  # noqa: BLE001 - validation reports the unknown step later
            allowed = set()
        step_defaults = kit.defaults.get(step.type)
        if isinstance(step_defaults, dict):
            _merge_defaults(
                params,
                {key: value for key, value in step_defaults.items() if key in allowed},
            )
        if hard.aspect_ratio and "aspect_ratio" in allowed:
            params["aspect_ratio"] = hard.aspect_ratio
        if hard.caption_preset and "preset" in allowed and not params.get("preset"):
            params["preset"] = hard.caption_preset
        if "caption_style" in allowed and not isinstance(
            params.get("caption_style"), (dict, type(None))
        ):
            params["caption_style"] = {}
        if kit.intro and "intro_path" in allowed and not params.get("intro_path"):
            params["intro_path"] = kit.intro
        if kit.outro and "outro_path" in allowed and not params.get("outro_path"):
            params["outro_path"] = kit.outro
        if kit.music and "music_path" in allowed and not params.get("music_path"):
            params["music_path"] = kit.music[0]
        if kit.lut and "lut_path" in allowed and not params.get("lut_path"):
            params["lut_path"] = kit.lut
        if hard.broll_style and "query" in allowed and not params.get("query"):
            params["query"] = hard.broll_style
    return updated
