"""Compact project brief and named checkpoints for OpenCode sessions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoflow.application.projects import (
    get_project,
    load_project_state,
    save_project_state,
)
from videoflow.application.revisions import (
    create_snapshot,
    list_snapshots,
    load_snapshot,
)
from videoflow.domain.errors import ProjectStateError


def _stage(state: Any) -> str:
    if not state.transcript:
        return "ingested"
    if not state.video_segments:
        return "transcribed"
    if state.overlays:
        return "edited"
    if state.pipeline.discard_sentence_ids:
        return "cleaned"
    return "timeline"


def _sources(state: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    roles = getattr(state, "source_roles", {}) or {}
    labels = getattr(state, "source_labels", {}) or {}
    for source_id, media in (state.sources or {}).items():
        fps = media.fps_num / media.fps_den if media.fps_den else 0.0
        items.append(
            {
                "id": source_id,
                "role": roles.get(source_id, "source"),
                "label": labels.get(source_id, Path(media.source_path).name),
                "duration_sec": round(
                    media.duration_frames / fps, 3
                ) if fps else 0.0,
                "fps": round(fps, 3),
                "audio": f"{media.audio_sample_rate // 1000}k/2ch",
            }
        )
    return items


def _gpu() -> dict[str, Any]:
    try:
        from videoflow.application.compute import compute_status

        status = compute_status()
    except Exception as exc:  # noqa: BLE001 - brief must never fail
        return {"status": "unknown", "error": str(exc)}
    return {
        "status": "remote" if status.get("available") else "local",
        "execution_node": status.get("execution_node", "local"),
        "transport": status.get("transport", "auto"),
        "gpu": status.get("gpu_name", ""),
        "vram_free_mb": status.get("vram_free_mb", 0),
    }


def _latest_qa(output: Path, limit: int = 3) -> list[dict[str, Any]]:
    root = Path(output) / "exports" / "qa"
    if not root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for pointer in sorted(root.glob("*/latest.json")):
        try:
            payload = json.loads(pointer.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            items.append(
                {
                    "artifact": pointer.parent.name,
                    "status": payload.get("status", ""),
                    "run_id": payload.get("run_id", ""),
                }
            )
        if len(items) >= limit:
            break
    return items


def _autonomy(record: Any, state: Any) -> str:
    try:
        from videoflow.application.brand_kit import load_brand_kit

        brand = load_brand_kit(record.channel_id or state.style_id)
        value = str(brand.get("autonomy_level") or "").strip().lower()
        if value in {"guided", "autonomous"}:
            return value
    except Exception:  # noqa: BLE001 - optional channel kit
        pass
    return "guided"


def _next_actions(state: Any) -> list[str]:
    if not state.transcript:
        return ["vf_ingest", "vf_transcript_query"]
    if not state.video_segments:
        return ["vf_beatmap_plan", "vf_timeline(apply_beatmap)"]
    if not (Path(state.media_info.source_path).is_file() if state.media_info else False):
        return ["vf_ingest"]
    return ["vf_preflight_plan", "vf_export", "vf_qa_final"]


def build_session_brief(project_id: str) -> dict[str, Any]:
    record = get_project(project_id)
    state = load_project_state(record)
    media = state.media_info
    fps = media.fps_num / media.fps_den if media and media.fps_den else 0.0
    duration = media.duration_frames / fps if media and fps else 0.0
    revisions = list_snapshots(record.output)[:3]
    return {
        "ok": True,
        "project_id": record.project_id,
        "name": record.name,
        "stage": _stage(state),
        "duration_sec": round(duration, 3),
        "fps": round(fps, 3),
        "sample_rate": media.audio_sample_rate if media else 0,
        "style": record.style_id or state.style_id,
        "autonomy": _autonomy(record, state),
        "sources": _sources(state),
        "gpu": _gpu(),
        "revision": state.revision,
        "last_revisions": [
            {
                "id": item.get("revision_id", ""),
                "label": item.get("reason", ""),
                "at": item.get("created_at", ""),
            }
            for item in revisions
        ],
        "last_qa": _latest_qa(Path(record.output)),
        "next_actions": _next_actions(state),
        "blockers": [],
    }


def checkpoints_path(output: Path) -> Path:
    return Path(output).expanduser() / "history" / "checkpoints.json"


def _read_checkpoints(output: Path) -> dict[str, Any]:
    path = checkpoints_path(output)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema_version": 1, "checkpoints": {}}
    if not isinstance(payload, dict):
        return {"schema_version": 1, "checkpoints": {}}
    payload.setdefault("schema_version", 1)
    if not isinstance(payload.get("checkpoints"), dict):
        payload["checkpoints"] = {}
    return payload


def _write_checkpoints(output: Path, payload: dict[str, Any]) -> None:
    path = checkpoints_path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def create_checkpoint(project_id: str, label: str) -> dict[str, Any]:
    text = str(label or "").strip()
    if not text:
        raise ProjectStateError("checkpoint label is required")
    record = get_project(project_id)
    state = load_project_state(record)
    revision_id = create_snapshot(
        record.output,
        state,
        reason=text,
        step="checkpoint",
    )
    payload = _read_checkpoints(Path(record.output))
    payload["checkpoints"][text] = {
        "revision_id": revision_id,
        "state_revision": state.revision,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    _write_checkpoints(Path(record.output), payload)
    return {
        "ok": True,
        "project_id": record.project_id,
        "label": text,
        "revision_id": revision_id,
        "revision": state.revision,
    }


def list_checkpoints(project_id: str) -> dict[str, Any]:
    record = get_project(project_id)
    payload = _read_checkpoints(Path(record.output))
    items = [
        {"label": label, **value}
        for label, value in sorted(payload["checkpoints"].items())
    ]
    return {
        "ok": True,
        "project_id": record.project_id,
        "checkpoints": items,
        "count": len(items),
    }


def restore_checkpoint(project_id: str, label: str) -> dict[str, Any]:
    record = get_project(project_id)
    payload = _read_checkpoints(Path(record.output))
    entry = payload["checkpoints"].get(str(label or "").strip())
    if not isinstance(entry, dict):
        raise ProjectStateError(f"Unknown checkpoint: {label}")
    revision_id = str(entry.get("revision_id") or "")
    if not revision_id:
        raise ProjectStateError(f"Checkpoint {label} has no revision id")
    restored = load_snapshot(record.output, revision_id)
    saved = save_project_state(
        record,
        restored,
        bump_revision=True,
        snapshot=True,
        snapshot_reason=f"before_restore_{label}",
        snapshot_step="restore_checkpoint",
    )
    return {
        "ok": True,
        "project_id": record.project_id,
        "label": str(label),
        "revision_id": revision_id,
        "revision": saved.revision,
    }


__all__ = [
    "build_session_brief",
    "checkpoints_path",
    "create_checkpoint",
    "list_checkpoints",
    "restore_checkpoint",
]
