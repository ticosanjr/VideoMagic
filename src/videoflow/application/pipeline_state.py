"""Serialize and restore the tools-only :class:`PipelineContext`.

The canonical project state owns the timeline and transcript. This module adds
the rest of the in-memory context (analysis spans, shorts, captions, artifacts,
metadata, and step checkpoints) so a later MCP call can resume from disk.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from videoflow.application.clock import now_iso_ms
from videoflow.application.time_map import build_time_map
from videoflow.core.context import PipelineContext
from videoflow.domain.state import PipelineCheckpoint, PipelineState, ProjectState

_MAX_JSON_BYTES = 2_000_000


def _json_safe(value: Any) -> Any:
    try:
        encoded = json.dumps(value, default=str)
    except Exception:  # noqa: BLE001 - metadata is advisory and may contain callables
        return None
    if len(encoded) > _MAX_JSON_BYTES:
        return None
    return json.loads(encoded)


def _short_payload(context: PipelineContext) -> list[dict[str, Any]]:
    rate = context.media.audio_sample_rate if context.media is not None else 48000
    payload: list[dict[str, Any]] = []
    for item in context.selected_shorts:
        if hasattr(item, "to_dict"):
            try:
                payload.append(_json_safe(item.to_dict(rate)) or {})
                continue
            except Exception:  # noqa: BLE001 - stale custom clip
                pass
        if isinstance(item, dict):
            payload.append(_json_safe(item) or {})
    return [item for item in payload if item]


def context_from_pipeline(
    context: PipelineContext,
    state: ProjectState,
    *,
    project_id: str = "",
    job_id: str = "",
) -> PipelineContext:
    """Fill a newly built context from the persisted project pipeline block."""

    from videoflow.application.shorts import short_clip_from_dict

    pipeline = state.pipeline
    context = context.model_copy(
        update={
            "pcm_path": Path(pipeline.pcm_path).expanduser() if pipeline.pcm_path else None,
            "pcm_digest": pipeline.pcm_digest,
            "speech_intervals": [tuple(item) for item in pipeline.speech_intervals],
            "silence_spans": list(pipeline.silence_spans),
            "retake_spans": list(pipeline.retake_spans),
            "retake_overlap_cuts": [tuple(item) for item in pipeline.retake_overlap_cuts],
            "inactive_spans": list(pipeline.inactive_spans),
            "vad_engine": pipeline.vad_engine,
            "transcript": list(state.transcript),
            "transcript_source": pipeline.transcript_source,
            "transcript_language": pipeline.transcript_language or state.language,
            "language_confidence": pipeline.language_confidence or state.language_confidence,
            "discard_sentence_ids": list(pipeline.discard_sentence_ids),
            "restored_sentence_ids": list(pipeline.restored_sentence_ids),
            "manual_overrides": list(pipeline.manual_overrides or state.manual_overrides),
            "shorts": [_json_safe(item) or {} for item in pipeline.shorts],
            "short_captions": dict(pipeline.short_captions),
            "warnings": list(pipeline.warnings),
            "artifacts": dict(pipeline.artifacts),
            "hashes": dict(pipeline.hashes),
            "cache_hits": list(pipeline.cache_hits),
            "cache_misses": list(pipeline.cache_misses),
            "metadata": {
                **dict(pipeline.metadata or {}),
                **({"project_id": project_id} if project_id else {}),
                **({"job_id": job_id} if job_id else {}),
            },
        }
    )
    selected = []
    for item in pipeline.selected_shorts:
        try:
            selected.append(short_clip_from_dict(item))
        except (TypeError, ValueError):
            continue
    context.selected_shorts = selected
    if not state.pipeline.time_map:
        context = context.model_copy(
            update={
                "state": state.model_copy(
                    update={
                        "pipeline": state.pipeline.model_copy(
                            update={"time_map": build_time_map(state)}
                        )
                    }
                )
            }
        )
    return context


def update_pipeline_from_context(
    state: ProjectState,
    context: PipelineContext,
    *,
    step: str = "",
    status: str = "completed",
    message: str = "",
    run_id: str = "",
    revision: int = 0,
) -> ProjectState:
    """Return ``state`` with the current context and one checkpoint persisted."""

    checkpoints = list(state.pipeline.checkpoints)
    if step:
        digest = hashlib.sha256(
            json.dumps(
                {"step": step, "status": status, "artifacts": context.artifacts},
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:16]
        checkpoints.append(
            PipelineCheckpoint(
                step=step,
                status=status,  # type: ignore[arg-type]
                started_at=state.pipeline.metadata.get("checkpoint_started_at", ""),
                finished_at=now_iso_ms(),
                params_hash=digest,
                revision=revision,
                message=message[:500],
            )
        )
        checkpoints = checkpoints[-200:]
    pipeline = PipelineState(
        run_id=run_id or state.pipeline.run_id,
        step=step or state.pipeline.step,
        applied_style_id=str(
            context.metadata.get("applied_style_id")
            or state.pipeline.applied_style_id
            or state.style_id
        ),
        artifacts={str(key): str(value) for key, value in context.artifacts.items() if value},
        metadata=_json_safe(context.metadata) or {},
        pcm_path=str(context.pcm_path) if context.pcm_path is not None else "",
        pcm_digest=context.pcm_digest,
        speech_intervals=[tuple(item) for item in context.speech_intervals],
        silence_spans=list(context.silence_spans),
        retake_spans=list(context.retake_spans),
        retake_overlap_cuts=[tuple(item) for item in context.retake_overlap_cuts],
        inactive_spans=list(context.inactive_spans),
        vad_engine=context.vad_engine,
        transcript_source=context.transcript_source,
        transcript_language=context.transcript_language,
        language_confidence=context.language_confidence,
        discard_sentence_ids=list(context.discard_sentence_ids),
        restored_sentence_ids=list(context.restored_sentence_ids),
        manual_overrides=list(context.manual_overrides),
        shorts=[_json_safe(item) or {} for item in context.shorts],
        selected_shorts=_short_payload(context),
        short_captions=dict(context.short_captions),
        warnings=list(context.warnings),
        hashes={str(key): str(value) for key, value in context.hashes.items() if value},
        cache_hits=list(context.cache_hits),
        cache_misses=list(context.cache_misses),
        time_map=build_time_map(context.state or state),
        checkpoints=checkpoints,
    )
    style_id = pipeline.applied_style_id or state.style_id
    return state.model_copy(
        update={
            "transcript": list(context.transcript),
            "manual_overrides": list(context.manual_overrides),
            "style_id": style_id,
            "language": context.transcript_language or state.language,
            "language_confidence": context.language_confidence
            if context.transcript_language
            else state.language_confidence,
            "pipeline": pipeline,
        }
    )


__all__ = ["context_from_pipeline", "update_pipeline_from_context"]
