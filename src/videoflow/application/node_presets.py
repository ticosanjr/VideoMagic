"""Per-node presets: built-ins, operator-created presets, and favorites."""

from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from videoflow.domain.errors import StateNotReadyError
from videoflow.runtime import portable_home

_LOCK = threading.RLock()

BUILTINS: dict[str, list[dict[str, object]]] = {
    "audio.vad": [
        {
            "name": "Gentle",
            "params": {
                "noise_db": -38,
                "speech_threshold": 0.4,
                "min_silence_ms": 550,
                "min_speech_ms": 150,
                "spike_suppression_ms": 260,
                "merge_gap_ms": 180,
                "pad_before_ms": 140,
                "pad_after_ms": 200,
            },
        },
        {
            "name": "Balanced",
            "params": {
                "noise_db": -30,
                "speech_threshold": 0.5,
                "min_silence_ms": 350,
                "min_speech_ms": 120,
                "spike_suppression_ms": 180,
                "merge_gap_ms": 120,
                "pad_before_ms": 80,
                "pad_after_ms": 120,
            },
        },
        {
            "name": "Aggressive",
            "params": {
                "noise_db": -24,
                "speech_threshold": 0.62,
                "min_silence_ms": 240,
                "min_speech_ms": 90,
                "spike_suppression_ms": 120,
                "merge_gap_ms": 70,
                "pad_before_ms": 40,
                "pad_after_ms": 60,
            },
        },
        {
            "name": "Tight",
            "params": {
                "noise_db": -20,
                "speech_threshold": 0.7,
                "min_silence_ms": 180,
                "min_speech_ms": 70,
                "spike_suppression_ms": 90,
                "merge_gap_ms": 40,
                "pad_before_ms": 20,
                "pad_after_ms": 30,
            },
        },
    ],
    "edit.timeline": [
        {
            "name": "Hard cut",
            "params": {"cut_mode": "hard", "enable_j_cuts": False, "enable_l_cuts": False},
        },
        {
            "name": "J-cut",
            "params": {"cut_mode": "j_cut", "enable_j_cuts": True, "enable_l_cuts": False},
        },
        {
            "name": "L-cut",
            "params": {"cut_mode": "l_cut", "enable_j_cuts": False, "enable_l_cuts": True},
        },
        {"name": "Custom", "params": {"cut_mode": "custom"}},
    ],
    "retakes.cull": [
        {"name": "Conservative", "params": {"strictness": "conservative", "strategy": "keep_best"}},
        {"name": "Balanced", "params": {"strictness": "balanced", "strategy": "keep_last"}},
        {"name": "Aggressive", "params": {"strictness": "aggressive", "strategy": "keep_last"}},
    ],
}


class NodePreset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    step_type: str
    name: str = Field(min_length=1, max_length=120)
    params: dict[str, object] = Field(default_factory=dict)
    favorite: bool = False
    builtin: bool = False
    created_at: str = ""


class NodePresetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_type: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    params: dict[str, object] = Field(default_factory=dict)


class NodePresetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    params: dict[str, object] | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _path() -> Path:
    return portable_home() / "node_presets.json"


def _read() -> dict[str, object]:
    try:
        payload = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"custom": [], "favorites": []}
    if not isinstance(payload, dict):
        return {"custom": [], "favorites": []}
    return payload


def _write(payload: dict[str, object]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "preset"


def _favorites() -> set[str]:
    raw = _read().get("favorites")
    return {str(item) for item in raw} if isinstance(raw, list) else set()


def list_presets(step_type: str = "") -> list[NodePreset]:
    favorites = _favorites()
    presets: list[NodePreset] = []
    for type_name, entries in BUILTINS.items():
        if step_type and type_name != step_type:
            continue
        for entry in entries:
            preset_id = f"builtin:{type_name}:{_slug(str(entry['name']))}"
            presets.append(
                NodePreset(
                    id=preset_id,
                    step_type=type_name,
                    name=str(entry["name"]),
                    params=dict(entry["params"]),
                    favorite=preset_id in favorites,
                    builtin=True,
                )
            )
    raw = _read().get("custom")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                preset = NodePreset.model_validate(item)
            except ValueError:
                continue
            if step_type and preset.step_type != step_type:
                continue
            preset.favorite = preset.id in favorites
            presets.append(preset)
    presets.sort(key=lambda item: (not item.favorite, item.name.lower()))
    return presets


def create_preset(request: NodePresetRequest) -> NodePreset:
    preset = NodePreset(
        id=f"preset-{uuid4().hex[:10]}",
        step_type=request.step_type,
        name=request.name.strip(),
        params=dict(request.params),
        created_at=_now(),
    )
    with _LOCK:
        payload = _read()
        custom = payload.get("custom")
        items = custom if isinstance(custom, list) else []
        items.append(preset.model_dump(mode="json"))
        payload["custom"] = items
        _write(payload)
    return preset


def update_preset(preset_id: str, request: NodePresetUpdate) -> NodePreset:
    with _LOCK:
        payload = _read()
        custom = payload.get("custom")
        items = custom if isinstance(custom, list) else []
        for index, item in enumerate(items):
            if isinstance(item, dict) and item.get("id") == preset_id:
                preset = NodePreset.model_validate(item)
                updated = preset.model_copy(
                    update={
                        "name": request.name.strip() if request.name else preset.name,
                        "params": request.params if request.params is not None else preset.params,
                    }
                )
                items[index] = updated.model_dump(mode="json")
                payload["custom"] = items
                _write(payload)
                return updated
    raise StateNotReadyError(f"Unknown node preset: {preset_id}")


def delete_preset(preset_id: str) -> None:
    with _LOCK:
        payload = _read()
        custom = payload.get("custom")
        items = custom if isinstance(custom, list) else []
        kept = [
            item
            for item in items
            if not (isinstance(item, dict) and item.get("id") == preset_id)
        ]
        if len(kept) == len(items):
            raise StateNotReadyError(f"Unknown node preset: {preset_id}")
        payload["custom"] = kept
        favorites = _favorites()
        favorites.discard(preset_id)
        payload["favorites"] = sorted(favorites)
        _write(payload)


def set_favorite(preset_id: str, favorite: bool) -> NodePreset:
    with _LOCK:
        payload = _read()
        favorites = _favorites()
        if favorite:
            favorites.add(preset_id)
        else:
            favorites.discard(preset_id)
        payload["favorites"] = sorted(favorites)
        _write(payload)
    for preset in list_presets():
        if preset.id == preset_id:
            preset.favorite = favorite
            return preset
    raise StateNotReadyError(f"Unknown node preset: {preset_id}")
