"""Local, server-side recipe organization: favorites, recents, and tags."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.clock import now_iso as _now
from videoflow.runtime import portable_home

DEFAULT_FAVORITES = frozenset(
    {
        "recut_replacement",
        "recut_replacement_retakes",
        "deepseek_full_edit",
        "autonomous_studio_master",
        "footage_intelligence_edit",
    }
)
_LOCK = threading.RLock()


class RecipeMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    favorite: bool = False
    last_used_at: str = ""
    use_count: int = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)


def meta_path() -> Path:
    return portable_home() / "recipe_meta.json"




def _read() -> dict[str, dict[str, object]]:
    path = meta_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): value
        for key, value in payload.items()
        if isinstance(value, dict)
    }


def _write(payload: dict[str, dict[str, object]]) -> None:
    path = meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def get_meta(recipe_id: str) -> RecipeMeta:
    raw = _read().get(recipe_id, {})
    payload = dict(raw)
    payload.setdefault("favorite", recipe_id in DEFAULT_FAVORITES)
    try:
        return RecipeMeta.model_validate(payload)
    except ValueError:
        return RecipeMeta(favorite=recipe_id in DEFAULT_FAVORITES)


def all_meta() -> dict[str, RecipeMeta]:
    ids = set(_read()) | DEFAULT_FAVORITES
    return {recipe_id: get_meta(recipe_id) for recipe_id in ids}


def set_favorite(recipe_id: str, favorite: bool) -> RecipeMeta:
    with _LOCK:
        payload = _read()
        entry = RecipeMeta.model_validate(
            {**payload.get(recipe_id, {}), "favorite": bool(favorite)}
        )
        payload[recipe_id] = entry.model_dump(mode="json")
        _write(payload)
        return entry


def touch(recipe_id: str, *, at: str | None = None) -> RecipeMeta:
    with _LOCK:
        payload = _read()
        current = get_meta(recipe_id)
        entry = current.model_copy(
            update={
                "last_used_at": at or _now(),
                "use_count": current.use_count + 1,
            }
        )
        payload[recipe_id] = entry.model_dump(mode="json")
        _write(payload)
        return entry


def set_tags(recipe_id: str, tags: list[str]) -> RecipeMeta:
    with _LOCK:
        clean = sorted({str(tag).strip() for tag in tags if str(tag).strip()})
        payload = _read()
        current = get_meta(recipe_id)
        entry = current.model_copy(update={"tags": clean})
        payload[recipe_id] = entry.model_dump(mode="json")
        _write(payload)
        return entry


def recent(recipe_ids: list[str], *, limit: int = 6) -> list[str]:
    metas = [(recipe_id, get_meta(recipe_id)) for recipe_id in recipe_ids]
    used = [(item.last_used_at, recipe_id) for recipe_id, item in metas if item.last_used_at]
    used.sort(reverse=True)
    return [recipe_id for _, recipe_id in used[: max(1, limit)]]


def decorate(items: list[dict[str, object]]) -> list[dict[str, object]]:
    """Attach metadata to recipe summaries without mutating the source list."""

    result: list[dict[str, object]] = []
    for item in items:
        recipe_id = str(item.get("id") or "")
        meta = get_meta(recipe_id)
        result.append(
            {
                **item,
                "favorite": meta.favorite,
                "last_used_at": meta.last_used_at,
                "use_count": meta.use_count,
                "tags": meta.tags,
            }
        )
    return result
