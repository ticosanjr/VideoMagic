"""LLM copilot for recipe drafts and timeline edit plans.

The model only proposes. Every proposal is validated against the same domain
rules as manual input, so a bad completion cannot bypass the engine.
"""

from __future__ import annotations

import json
from typing import Any

from videoflow.adapters import LlmClient
from videoflow.core.recipe import Recipe, parse_recipe
from videoflow.domain.errors import RecipeError, StateNotReadyError
from videoflow.steps import requirements_by_type, step_types

RECIPE_PROMPT = """\
Design a VideoFlow recipe as JSON. Use only these step types and respect their
dependencies. Return only the recipe object with schema_version, id, name,
description, and steps. Steps have id, type, needs, params, and enabled.

Available steps:
{steps}

Request: {prompt}
"""

EDIT_PROMPT = """\
Propose timeline edits as JSON: {{"edits":[{{"clip_id":"...","action":"...",...}}],
"reasoning":"..."}}. Allowed actions: trim (start_sec,end_sec), move (delta_sec),
split (split_sec), delete, ripple, ripple_trim (start_sec,end_sec), slip
(delta_sec), slide (delta_sec), duplicate. Use only clip ids that exist.

Timeline:
{timeline}

Request: {prompt}
"""


def _steps_manifest() -> str:
    from videoflow.steps import manifest

    lines = []
    for entry in manifest():
        params = entry.get("params", {})
        lines.append(f"- {entry.get('type')}: {json.dumps(params, ensure_ascii=False)}")
    return "\n".join(lines)


def propose_recipe(client: LlmClient, prompt: str) -> Recipe:
    if not prompt.strip():
        raise RecipeError("Describe the recipe you want.")
    raw = client.complete_json(
        RECIPE_PROMPT.format(steps=_steps_manifest(), prompt=prompt.strip()),
        "videoflow.recipe",
    )
    if not isinstance(raw, dict):
        raise RecipeError("The model did not return a recipe object.")
    raw.setdefault("schema_version", 1)
    raw.setdefault("id", "copilot_recipe")
    raw.setdefault("name", "Copilot recipe")
    raw.setdefault("description", prompt.strip()[:200])
    try:
        recipe = parse_recipe(raw)
        recipe.validate_graph(
            step_types(), requires_by_type=requirements_by_type()
        )
    except Exception as exc:
        raise RecipeError(f"The proposed recipe is invalid: {exc}") from exc
    return recipe


ALLOWED_ACTIONS = {
    "trim",
    "move",
    "split",
    "delete",
    "ripple",
    "ripple_trim",
    "slip",
    "slide",
    "duplicate",
}


def propose_timeline_edits(
    client: LlmClient, prompt: str, clips: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not prompt.strip():
        raise StateNotReadyError("Describe the edit you want.")
    if not clips:
        raise StateNotReadyError("There are no clips to edit.")
    payload = [
        {
            "clip_id": clip.get("id"),
            "start_sec": clip.get("start_sec"),
            "end_sec": clip.get("end_sec"),
        }
        for clip in clips[:200]
    ]
    raw = client.complete_json(
        EDIT_PROMPT.format(
            timeline=json.dumps(payload, ensure_ascii=False), prompt=prompt.strip()
        ),
        "videoflow.timeline_edit",
    )
    edits = raw.get("edits") if isinstance(raw, dict) else None
    if not isinstance(edits, list) or not edits:
        raise StateNotReadyError("The model returned no usable edits.")
    ids = {str(clip.get("id")) for clip in clips}
    cleaned: list[dict[str, Any]] = []
    for item in edits:
        if not isinstance(item, dict):
            continue
        clip_id = str(item.get("clip_id") or "")
        action = str(item.get("action") or "")
        if clip_id not in ids or action not in ALLOWED_ACTIONS:
            raise StateNotReadyError(
                f"The model proposed an unsupported edit: {clip_id}/{action}"
            )
        cleaned.append(dict(item))
    if not cleaned:
        raise StateNotReadyError("The model returned no usable edits.")
    return cleaned
