"""Light state index and SHA-256 sidecars for the v4 project layout.

``state.json`` stays small (metadata, revision, sidecar pointers). The heavy
documents live in ``sidecars/`` and are addressed by SHA-256. The legacy
``project_state.json`` remains the compatibility cache for callers that still
read the monolithic document directly.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from videoflow.application.clock import now_iso_ms
from videoflow.core.media_contract import PIPELINE_SCHEMA_VERSION
from videoflow.domain.state import ProjectState

SIDECAR_SCHEMA_VERSION = 4
_HEAVY_KEYS = frozenset(
    {
        "transcript",
        "vad_intervals",
        "video_segments",
        "audio_segments",
        "inactive_segments",
        "overlays",
        "vertical_clips",
        "pipeline",
    }
)


def sidecar_dir(output: Path | str) -> Path:
    path = Path(output).expanduser() / "sidecars"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: object) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    raw = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    temporary.write_bytes(raw)
    os.replace(temporary, path)
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _pointer(path: Path, *, output: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(output).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _written_pointer(path: Path, info: dict[str, Any], *, output: Path) -> dict[str, Any]:
    return {"path": path.relative_to(output).as_posix(), **info}


def _sentences_payload(state: ProjectState, name: str) -> dict[str, Any]:
    return {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "pipeline_schema_version": PIPELINE_SCHEMA_VERSION,
        "name": name,
        "sentences": [sentence.model_dump(mode="json") for sentence in state.transcript],
    }


def _timeline_payload(state: ProjectState) -> dict[str, Any]:
    return {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "pipeline_schema_version": PIPELINE_SCHEMA_VERSION,
        "vad_intervals": [item.model_dump(mode="json") for item in state.vad_intervals],
        "video_segments": [item.model_dump(mode="json") for item in state.video_segments],
        "audio_segments": [item.model_dump(mode="json") for item in state.audio_segments],
        "inactive_segments": [
            item.model_dump(mode="json") for item in state.inactive_segments
        ],
        "overlays": [item.model_dump(mode="json") for item in state.overlays],
        "vertical_clips": [
            item.model_dump(mode="json") for item in state.vertical_clips
        ],
    }


def _core_payload(state: ProjectState) -> dict[str, Any]:
    payload = state.model_dump(mode="json")
    for key in _HEAVY_KEYS:
        payload.pop(key, None)
    payload["schema_version"] = SIDECAR_SCHEMA_VERSION
    payload["pipeline_schema_version"] = PIPELINE_SCHEMA_VERSION
    return payload


def _qa_pointers(output: Path) -> list[dict[str, Any]]:
    root = output / "exports" / "qa"
    if not root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        if not path.is_file():
            continue
        items.append(_pointer(path, output=output))
    return items[-40:]


def write_state_index(output: Path | str, state: ProjectState) -> dict[str, Any]:
    """Write the lightweight index and every sidecar atomically."""

    root = Path(output).expanduser()
    folder = sidecar_dir(root)
    sidecars: dict[str, dict[str, Any]] = {}

    core = folder / "core.json"
    sidecars["core"] = _written_pointer(
        core, _write_json(core, _core_payload(state)), output=root
    )

    for name in ("transcript_raw", "transcript_clean"):
        path = folder / f"{name}.json"
        sidecars[name] = {
            **_written_pointer(
                path, _write_json(path, _sentences_payload(state, name)), output=root
            ),
            "sentences": len(state.transcript),
        }

    timeline = folder / "timeline.json"
    sidecars["timeline"] = {
        **_written_pointer(
            timeline, _write_json(timeline, _timeline_payload(state)), output=root
        ),
        "segments": len(state.video_segments),
    }

    pipeline = folder / "pipeline.json"
    sidecars["pipeline"] = _written_pointer(
        pipeline,
        _write_json(
            pipeline,
            {
                "schema_version": SIDECAR_SCHEMA_VERSION,
                "pipeline_schema_version": PIPELINE_SCHEMA_VERSION,
                "pipeline": state.pipeline.model_dump(mode="json"),
            },
        ),
        output=root,
    )

    scenes = root / "scenes" / "scenes.json"
    if not scenes.is_file():
        scenes = root / "scenes_manifest.json"
    if scenes.is_file():
        sidecars["scenes_manifest"] = _pointer(scenes, output=root)

    slug = str(state.pipeline.metadata.get("slug") or "") or str(state.project_id)
    index = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "pipeline_schema_version": PIPELINE_SCHEMA_VERSION,
        "project_id": str(state.project_id),
        "slug": slug,
        "revision": state.revision,
        "updated_at": now_iso_ms(),
        "sidecars": sidecars,
        "qa": _qa_pointers(root),
    }
    _write_json(root / "state.json", index)
    return index


def read_state_index(output: Path | str) -> dict[str, Any]:
    path = Path(output).expanduser() / "state.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_sidecar(output: Path, index: dict[str, Any], name: str) -> dict[str, Any]:
    pointer = (index.get("sidecars") or {}).get(name)
    if not isinstance(pointer, dict):
        return {}
    path = output / str(pointer.get("path") or "")
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_state_from_index(output: Path | str) -> ProjectState | None:
    """Merge the light index and sidecars into the in-memory aggregate."""

    root = Path(output).expanduser()
    index = read_state_index(root)
    if not index or not index.get("sidecars"):
        return None
    core = _read_sidecar(root, index, "core")
    if not core:
        return None
    core.pop("pipeline_schema_version", None)
    timeline = _read_sidecar(root, index, "timeline")
    pipeline = _read_sidecar(root, index, "pipeline")
    transcript = _read_sidecar(root, index, "transcript_raw")
    merged = {
        **core,
        "transcript": transcript.get("sentences") or [],
        "vad_intervals": timeline.get("vad_intervals") or [],
        "video_segments": timeline.get("video_segments") or [],
        "audio_segments": timeline.get("audio_segments") or [],
        "inactive_segments": timeline.get("inactive_segments") or [],
        "overlays": timeline.get("overlays") or [],
        "vertical_clips": timeline.get("vertical_clips") or [],
        "pipeline": pipeline.get("pipeline") or {},
    }
    try:
        return ProjectState.model_validate(merged)
    except (TypeError, ValueError):
        return None


__all__ = [
    "SIDECAR_SCHEMA_VERSION",
    "load_state_from_index",
    "read_state_index",
    "sidecar_dir",
    "write_state_index",
]
