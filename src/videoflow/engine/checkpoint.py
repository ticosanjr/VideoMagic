"""Per-step checkpoints for resume and step-scoped runs.

The manifest is the cache index. The snapshot contains only the mutable
context fields a downstream step needs; paths and the current run's cache
counters stay owned by the runner.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from videoflow.application.shorts import short_clip_from_dict
from videoflow.core.context import PipelineContext

CHECKPOINT_VERSION = 1

SNAPSHOT_FIELDS = (
    "media",
    "pcm_path",
    "pcm_digest",
    "speech_intervals",
    "vad_engine",
    "transcript",
    "transcript_source",
    "discard_sentence_ids",
    "restored_sentence_ids",
    "manual_overrides",
    "state",
    "shorts",
    "warnings",
    "artifacts",
    "short_captions",
    "hashes",
    "metadata",
)


def step_dir(output: Path, step_id: str) -> Path:
    return output / "work" / "steps" / step_id


def source_fingerprint(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return str(path)
    return f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"


def snapshot_context(context: PipelineContext) -> dict[str, Any]:
    payload = context.model_dump(mode="json")
    for key in (
        "source",
        "output",
        "work",
        "exports",
        "cache_hits",
        "cache_misses",
        "selected_shorts",
    ):
        payload.pop(key, None)
    rate = context.media.audio_sample_rate if context.media is not None else 48000
    payload["selected_shorts"] = [
        clip.to_dict(rate) for clip in context.selected_shorts
    ]
    return payload


def restore_context(context: PipelineContext, snapshot: dict[str, Any]) -> None:
    payload = snapshot.get("context")
    if not isinstance(payload, dict):
        raise ValueError("checkpoint has no context object")
    cache_hits = list(context.cache_hits)
    cache_misses = list(context.cache_misses)
    run_id = context.metadata.get("run_id")
    base = {
        "source": context.source,
        "output": context.output,
        "work": context.work,
        "exports": context.exports,
        **payload,
    }
    restored = PipelineContext.model_validate(base)
    for field in SNAPSHOT_FIELDS:
        setattr(context, field, getattr(restored, field))
    context.cache_hits = cache_hits
    context.cache_misses = cache_misses
    if run_id is not None:
        context.metadata["run_id"] = run_id
    context.metadata.pop("failed_step", None)
    selected = payload.get("selected_shorts") or []
    context.selected_shorts = [
        short_clip_from_dict(item) for item in selected if isinstance(item, dict)
    ]


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
