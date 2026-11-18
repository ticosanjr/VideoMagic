"""Timeline edit, metadata, snapshot, overlay, and waveform routes."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from videoflow.api.errors import status_for
from videoflow.application.broll_approval import load_approvals
from videoflow.application.jobs import Job, JobManager
from videoflow.application.live_source import live_sources
from videoflow.application.render_inputs import read_filters
from videoflow.application.state_cache import load_state
from videoflow.application.timeline_edit import TimelineEdit, apply_timeline_edit
from videoflow.application.timeline_history import TimelineHistory
from videoflow.application.timeline_meta import (
    TimelineMeta,
    TrackState,
    add_comment,
    add_marker,
    comments_for,
    load_meta,
    remove_comment,
    remove_marker,
    save_meta,
    set_track,
)
from videoflow.application.timeline_snapshots import (
    delete_snapshot,
    import_snapshot,
    list_snapshots,
    read_snapshot,
    save_snapshot,
    snapshot_path,
)
from videoflow.application.waveforms import peaks_for_range
from videoflow.domain.errors import (
    IngestError,
    StateNotReadyError,
    TranscriptNotFoundError,
    VideoFlowError,
)
from videoflow.domain.paths import resolve_allowed
from videoflow.domain.state import ProjectState, Transition
from videoflow.runtime import allowed_roots


def fail(exc: VideoFlowError) -> None:
    raise HTTPException(status_code=status_for(exc.code), detail=exc.to_dict()) from exc


class LenientJsonBody(BaseModel):
    """Accept a JSON object even when a client double-encoded the body."""

    @model_validator(mode="before")
    @classmethod
    def decode_body(cls, value: Any) -> Any:
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8", "replace")
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except ValueError as exc:
                raise ValueError("body must be a JSON object") from exc
            if not isinstance(parsed, dict):
                raise ValueError("body must be a JSON object")
            return parsed
        return value


class OverlayRequest(BaseModel):
    overlay_id: str = Field(default="", max_length=60)
    asset_id: str = Field(default="", max_length=120)
    path: str = Field(min_length=1)
    start_sec: float = Field(ge=0.0)
    duration_sec: float = Field(gt=0.0, le=3600.0)
    anchor: Literal[
        "top_left",
        "top_center",
        "top_right",
        "bottom_left",
        "bottom_center",
        "bottom_right",
        "center",
    ] = "top_center"
    margin_x: int = Field(default=0, ge=0)
    margin_y: int = Field(default=0, ge=0)
    width_ratio: float = Field(default=0.25, gt=0.0, le=1.0)
    z: int = Field(default=20, ge=0, le=1000)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    kind: Literal["image", "video"] = "image"


class ClipCommentRequest(BaseModel):
    clip_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2000)
    author: str = Field(default="", max_length=120)
    id: str = Field(default="", max_length=60)


class TimelineEditRequest(LenientJsonBody):
    clip_id: str = Field(min_length=1)
    action: Literal[
        "trim", "move", "delete", "split", "ripple", "ripple_trim", "slip",
        "slide", "duplicate", "deactivate", "activate", "recut",
    ]
    start_sec: float | None = Field(default=None, ge=0.0)
    end_sec: float | None = Field(default=None, ge=0.0)
    delta_sec: float = 0.0
    split_sec: float | None = Field(default=None, ge=0.0)


class ClipUpdateRequest(LenientJsonBody):
    transition_type: Literal["crossfade", "fade_to_black", "none"] | None = None
    transition_duration_frames: int | None = Field(default=None, ge=1, le=120)
    scale: float | None = Field(default=None, ge=1.0, le=3.0)
    pos_x: float | None = Field(default=None, ge=-1.0, le=1.0)
    pos_y: float | None = Field(default=None, ge=-1.0, le=1.0)
    fade_in_sec: float | None = Field(default=None, ge=0.0, le=30.0)
    fade_out_sec: float | None = Field(default=None, ge=0.0, le=30.0)


class ClipBatchStyleRequest(ClipUpdateRequest):
    clip_ids: list[str] = Field(min_length=1, max_length=200)


class MarkerRequest(LenientJsonBody):
    time_sec: float = Field(ge=0.0)
    end_sec: float = Field(default=0.0, ge=0.0)
    label: str = Field(default="", max_length=300)
    color: str = Field(default="#38bdf8", max_length=20)


class TimelineBatchRequest(LenientJsonBody):
    edits: list[TimelineEditRequest] = Field(min_length=1, max_length=200)


class TimelineSnapshotRequest(BaseModel):
    name: str = Field(default="", max_length=120)


class TimelineSnapshotLoadRequest(BaseModel):
    job_id: str = Field(min_length=1)


class TimelineSnapshotImportRequest(BaseModel):
    payload: dict[str, Any]
    name: str = Field(default="", max_length=120)
    job_id: str = Field(default="", max_length=120)


class CaptionUpdateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _timeline_etag(revision: int) -> str:
    return f'"timeline-{revision}"'


def _require_if_match(request: Request | None, revision: int) -> None:
    if request is None:
        return
    header = (request.headers.get("if-match") or "").strip()
    if not header or header == "*":
        return
    candidates = [item.strip() for item in header.split(",")]
    if _timeline_etag(revision) in candidates:
        return
    raise HTTPException(
        status_code=412,
        detail={
            "ok": False,
            "code": "precondition_failed",
            "message": (
                "The timeline changed since it was loaded. Refresh the timeline "
                "and reapply the edit."
            ),
            "details": {"etag": _timeline_etag(revision)},
        },
    )


def _timeline_state_path(job: Job) -> Path:
    return Path(
        str((job.result or {}).get("state_path") or job.output / "project_state.json")
    )


def _timeline_history(job: Job) -> TimelineHistory:
    return TimelineHistory(job.output / "timeline_history.json")


def _apply_and_store(
    job: Job,
    state: ProjectState,
    state_path: Path,
    history: TimelineHistory,
    revision: int,
) -> ProjectState:
    state = state.model_copy(update={"revision": revision})
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return state


def _assert_tracks_unlocked(job: Job, tracks: set[str]) -> None:
    meta = load_meta(job.output)
    locked = {
        name
        for name, state in meta.tracks.items()
        if state.locked and (not tracks or name in tracks)
    }
    if locked:
        raise StateNotReadyError(
            "The timeline track is locked. Unlock it before editing: "
            + ", ".join(sorted(locked))
        )


def _apply_clip_style(
    state: ProjectState, clip_id: str, request: ClipUpdateRequest
) -> None:
    video = next(
        (clip for clip in state.video_segments if clip.clip_id == clip_id), None
    )
    audio = next(
        (clip for clip in state.audio_segments if clip.clip_id == clip_id), None
    )
    if video is None and audio is None:
        raise StateNotReadyError(f"Unknown clip: {clip_id}")
    if video is not None:
        if request.transition_type is not None:
            if request.transition_type == "none":
                video.transition_out = None
            else:
                video.transition_out = Transition(
                    type=request.transition_type,
                    duration_frames=request.transition_duration_frames
                    or (
                        video.transition_out.duration_frames
                        if video.transition_out
                        else 6
                    ),
                )
        video.transform = video.transform.model_copy(
            update={
                key: value
                for key, value in {
                    "scale": request.scale,
                    "pos_x": request.pos_x,
                    "pos_y": request.pos_y,
                }.items()
                if value is not None
            }
        )
    if audio is not None:
        rate = (
            state.media_info.audio_sample_rate
            if state.media_info is not None
            else 48000
        )
        if request.fade_in_sec is not None:
            audio.fade_in_samples = round(request.fade_in_sec * rate)
        if request.fade_out_sec is not None:
            audio.fade_out_samples = round(request.fade_out_sec * rate)


def _live_titles(output: Path) -> tuple[list[dict[str, object]], bool]:
    """Read structured title cues; ASS alone cannot be composed in-browser."""

    ass = output / "titles.ass"
    source = output / "titles.json"
    if not source.is_file():
        return [], not ass.is_file()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], not ass.is_file()
    cues: list[dict[str, object]] = []
    for card in payload.get("title_cards", []) if isinstance(payload, dict) else []:
        if not isinstance(card, dict) or card.get("kind") == "short":
            continue
        text = str(card.get("text") or "").strip()
        if not text:
            continue
        start = max(0.0, float(card.get("start_sec") or 0.0))
        duration = max(0.5, float(card.get("duration_sec") or 2.0))
        cues.append(
            {
                "start_sec": round(start, 3),
                "end_sec": round(start + duration, 3),
                "text": text,
                "style": "title",
            }
        )
    for item in payload.get("lower_thirds", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        start = max(0.0, float(item.get("start_sec") or 0.0))
        end = max(start + 0.5, float(item.get("end_sec") or start + 3.0))
        cues.append(
            {
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "text": text,
                "style": "lower_third",
            }
        )
    return sorted(cues, key=lambda cue: float(cue["start_sec"])), True


def _live_playback(
    state: ProjectState, _meta: object
) -> tuple[bool, str]:
    media = state.media_info
    if media is None:
        return False, "no media info"
    source = Path(media.source_path).expanduser()
    if not source.is_file():
        return False, "source media is offline"
    video = sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
    audio = {clip.clip_id: clip for clip in state.audio_segments}
    for clip in video:
        transform = clip.transform
        if (
            abs(float(transform.scale) - 1.0) > 0.0001
            or abs(float(transform.pos_x)) > 0.0001
            or abs(float(transform.pos_y)) > 0.0001
            or transform.keyframes
            or transform.type != "none"
        ):
            return False, "clip transforms require the rendered preview"
        if clip.clip_id not in audio:
            return False, "audio/video segments are not paired"
    return True, "transitions, overlays, and titles are live"


def register_timeline_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register timeline edit, metadata, snapshot, overlay, and waveform routes."""

    @app.patch("/api/v1/jobs/{job_id}/timeline")
    def edit_job_timeline(
        job_id: str, request: TimelineEditRequest, http_request: Request
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
            _assert_tracks_unlocked(job, set())
            state_path = _timeline_state_path(job)
            history = _timeline_history(job)
            state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
            _require_if_match(http_request, state.revision)
            previous = state.model_copy(deep=True)
            state = apply_timeline_edit(
                state,
                TimelineEdit(
                    clip_id=request.clip_id,
                    action=request.action,
                    start_sec=request.start_sec,
                    end_sec=request.end_sec,
                    delta_sec=request.delta_sec,
                    split_sec=request.split_sec,
                ),
            )
            history.record(previous)
            state = _apply_and_store(
                job, state, state_path, history, previous.revision + 1
            )
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "timeline_invalid", "message": str(exc)},
            ) from exc
        return {
            "ok": True,
            "revision": state.revision,
            "etag": _timeline_etag(state.revision),
            "can_undo": history.can_undo,
            "can_redo": history.can_redo,
            "warning": "Re-run export/render to refresh artifacts.",
        }

    @app.patch("/api/v1/jobs/{job_id}/timeline/clips")
    def update_timeline_clips(
        job_id: str, request: ClipBatchStyleRequest, http_request: Request
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        locked_scopes: set[str] = set()
        if (
            request.transition_type is not None
            or request.scale is not None
            or request.pos_x is not None
            or request.pos_y is not None
        ):
            locked_scopes.add("video")
        if request.fade_in_sec is not None or request.fade_out_sec is not None:
            locked_scopes.add("audio")
        _assert_tracks_unlocked(job, locked_scopes)
        state_path = _timeline_state_path(job)
        history = _timeline_history(job)
        state = ProjectState.model_validate_json(
            state_path.read_text(encoding="utf-8")
        )
        _require_if_match(http_request, state.revision)
        previous = state.model_copy(deep=True)
        known = {clip.clip_id for clip in state.video_segments} | {
            clip.clip_id for clip in state.audio_segments
        }
        clip_ids = list(dict.fromkeys(request.clip_ids))
        missing = [clip_id for clip_id in clip_ids if clip_id not in known]
        if missing:
            raise StateNotReadyError(
                f"Unknown clip(s): {', '.join(missing)}"
            )
        for clip_id in clip_ids:
            _apply_clip_style(state, clip_id, request)
        history.record(previous)
        state = _apply_and_store(
            job, state, state_path, history, previous.revision + 1
        )
        return {
            "ok": True,
            "revision": state.revision,
            "applied": len(clip_ids),
            "etag": _timeline_etag(state.revision),
            "can_undo": history.can_undo,
            "can_redo": history.can_redo,
            "warning": "Re-run export/render to refresh artifacts.",
        }

    @app.patch("/api/v1/jobs/{job_id}/timeline/clip/{clip_id}")
    def update_timeline_clip(
        job_id: str, clip_id: str, request: ClipUpdateRequest, http_request: Request
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        locked_scopes: set[str] = set()
        if (
            request.transition_type is not None
            or request.scale is not None
            or request.pos_x is not None
            or request.pos_y is not None
        ):
            locked_scopes.add("video")
        if request.fade_in_sec is not None or request.fade_out_sec is not None:
            locked_scopes.add("audio")
        _assert_tracks_unlocked(job, locked_scopes)
        state_path = _timeline_state_path(job)
        history = _timeline_history(job)
        state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        _require_if_match(http_request, state.revision)
        previous = state.model_copy(deep=True)
        _apply_clip_style(state, clip_id, request)
        history.record(previous)
        state = _apply_and_store(
            job, state, state_path, history, previous.revision + 1
        )
        return {
            "ok": True,
            "revision": state.revision,
            "etag": _timeline_etag(state.revision),
            "can_undo": history.can_undo,
            "can_redo": history.can_redo,
            "warning": "Re-run export/render to refresh artifacts.",
        }

    @app.patch("/api/v1/jobs/{job_id}/timeline/batch")
    def edit_job_timeline_batch(
        job_id: str, request: TimelineBatchRequest, http_request: Request
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
            _assert_tracks_unlocked(job, set())
            state_path = _timeline_state_path(job)
            history = _timeline_history(job)
            current = ProjectState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            )
            _require_if_match(http_request, current.revision)
            previous = current.model_copy(deep=True)
            working = current.model_copy(deep=True)
            for item in request.edits:
                working = apply_timeline_edit(
                    working,
                    TimelineEdit(
                        clip_id=item.clip_id,
                        action=item.action,
                        start_sec=item.start_sec,
                        end_sec=item.end_sec,
                        delta_sec=item.delta_sec,
                        split_sec=item.split_sec,
                    ),
                )
            history.record(previous)
            state = _apply_and_store(
                job, working, state_path, history, previous.revision + 1
            )
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "timeline_invalid", "message": str(exc)},
            ) from exc
        return {
            "ok": True,
            "revision": state.revision,
            "etag": _timeline_etag(state.revision),
            "applied": len(request.edits),
            "can_undo": history.can_undo,
            "can_redo": history.can_redo,
            "warning": "Re-run export/render to refresh artifacts.",
        }

    @app.post("/api/v1/jobs/{job_id}/timeline/undo")
    def undo_job_timeline(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        state_path = _timeline_state_path(job)
        history = _timeline_history(job)
        current = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        restored = history.undo_state(current)
        if restored is None:
            raise StateNotReadyError("Nothing to undo.")
        state = _apply_and_store(
            job, restored, state_path, history, current.revision + 1
        )
        return {
            "ok": True,
            "revision": state.revision,
            "can_undo": history.can_undo,
            "can_redo": history.can_redo,
        }

    @app.post("/api/v1/jobs/{job_id}/timeline/redo")
    def redo_job_timeline(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        state_path = _timeline_state_path(job)
        history = _timeline_history(job)
        current = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        restored = history.redo_state(current)
        if restored is None:
            raise StateNotReadyError("Nothing to redo.")
        state = _apply_and_store(
            job, restored, state_path, history, current.revision + 1
        )
        return {
            "ok": True,
            "revision": state.revision,
            "can_undo": history.can_undo,
            "can_redo": history.can_redo,
        }

    @app.patch("/api/v1/jobs/{job_id}/captions/{sentence_id}")
    def update_job_caption(
        job_id: str, sentence_id: int, request: CaptionUpdateRequest
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
            state_path = Path(
                str((job.result or {}).get("state_path") or job.output / "project_state.json")
            )
            state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
            previous = state.model_copy(deep=True)
            history = _timeline_history(job)
            found = False
            for sentence in state.transcript:
                if sentence.id == sentence_id:
                    sentence.text = request.text
                    found = True
                    break
            if not found:
                raise TranscriptNotFoundError(f"Sentence {sentence_id}")
            history.record(previous)
            state = _apply_and_store(
                job, state, state_path, history, previous.revision + 1
            )
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "timeline_invalid", "message": str(exc)},
            ) from exc
        return {
            "ok": True,
            "sentence_id": sentence_id,
            "text": request.text,
            "revision": state.revision,
            "can_undo": history.can_undo,
            "can_redo": history.can_redo,
        }

    @app.get("/api/v1/jobs/{job_id}/timeline/meta")
    def job_timeline_meta(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        return {"ok": True, **load_meta(job.output).model_dump(mode="json")}

    @app.put("/api/v1/jobs/{job_id}/timeline/meta")
    def replace_job_timeline_meta(
        job_id: str, request: TimelineMeta
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        meta = save_meta(job.output, request)
        return {"ok": True, **meta.model_dump(mode="json")}

    @app.post("/api/v1/jobs/{job_id}/timeline/markers", status_code=201)
    def create_job_marker(job_id: str, request: MarkerRequest) -> dict[str, object]:
        job = jobs.get(job_id)
        marker = add_marker(
            job.output,
            marker_id=(
                f"m-{int(request.time_sec * 1000)}-"
                f"{len(load_meta(job.output).markers) + 1}"
            ),
            time_sec=request.time_sec,
            end_sec=request.end_sec,
            label=request.label,
            color=request.color,
        )
        return {"ok": True, "markers": [item.model_dump(mode="json") for item in marker.markers]}

    @app.delete("/api/v1/jobs/{job_id}/timeline/markers/{marker_id}")
    def delete_job_marker(job_id: str, marker_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        meta = remove_marker(job.output, marker_id)
        return {"ok": True, "markers": [item.model_dump(mode="json") for item in meta.markers]}

    @app.post("/api/v1/jobs/{job_id}/timeline/overlays", status_code=201)
    def create_timeline_overlay(job_id: str, request: OverlayRequest) -> dict[str, object]:
        from videoflow.domain.state import OverlayClip

        job = jobs.get(job_id)
        _assert_tracks_unlocked(job, {"video"})
        resolved = resolve_allowed(Path(request.path), allowed_roots())
        state_path = _timeline_state_path(job)
        history = _timeline_history(job)
        state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        previous = state.model_copy(deep=True)
        fps = (
            state.media_info.fps_num / state.media_info.fps_den
            if state.media_info is not None
            else 30.0
        )
        overlay = OverlayClip(
            overlay_id=request.overlay_id or f"overlay-{int(time.time() * 1000)}",
            asset_id=request.asset_id,
            path=str(resolved),
            start_frame=round(request.start_sec * fps),
            duration_frames=max(1, round(request.duration_sec * fps)),
            anchor=request.anchor,
            margin_x=request.margin_x,
            margin_y=request.margin_y,
            width_ratio=request.width_ratio,
            z=request.z,
            opacity=request.opacity,
            kind=request.kind,
        )
        state.overlays = [
            item for item in state.overlays if item.overlay_id != overlay.overlay_id
        ] + [overlay]
        history.record(previous)
        state = _apply_and_store(job, state, state_path, history, previous.revision + 1)
        return {
            "ok": True,
            "revision": state.revision,
            "overlays": [item.model_dump(mode="json") for item in state.overlays],
        }

    @app.delete("/api/v1/jobs/{job_id}/timeline/overlays/{overlay_id}")
    def delete_timeline_overlay(job_id: str, overlay_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        _assert_tracks_unlocked(job, {"video"})
        state_path = _timeline_state_path(job)
        history = _timeline_history(job)
        state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        previous = state.model_copy(deep=True)
        kept = [item for item in state.overlays if item.overlay_id != overlay_id]
        if len(kept) == len(state.overlays):
            raise StateNotReadyError(f"Unknown overlay: {overlay_id}")
        state.overlays = kept
        history.record(previous)
        state = _apply_and_store(job, state, state_path, history, previous.revision + 1)
        return {
            "ok": True,
            "revision": state.revision,
            "overlays": [item.model_dump(mode="json") for item in state.overlays],
        }

    @app.get("/api/v1/jobs/{job_id}/timeline/comments")
    def list_clip_comments(job_id: str, clip_id: str = "") -> dict[str, object]:
        job = jobs.get(job_id)
        return {"ok": True, "comments": comments_for(job.output, clip_id)}

    @app.post("/api/v1/jobs/{job_id}/timeline/comments", status_code=201)
    def create_clip_comment(job_id: str, request: ClipCommentRequest) -> dict[str, object]:
        job = jobs.get(job_id)
        meta = add_comment(
            job.output,
            comment_id=request.id or f"comment-{int(time.time() * 1000)}",
            clip_id=request.clip_id,
            text=request.text,
            author=request.author,
        )
        return {"ok": True, "comments": [item.model_dump() for item in meta.comments]}

    @app.delete("/api/v1/jobs/{job_id}/timeline/comments/{comment_id}")
    def delete_clip_comment(job_id: str, comment_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        meta = remove_comment(job.output, comment_id)
        return {"ok": True, "comments": [item.model_dump() for item in meta.comments]}

    @app.put("/api/v1/jobs/{job_id}/timeline/tracks/{track}")
    def update_job_track(
        job_id: str, track: str, request: TrackState
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        meta = set_track(job.output, track, request)
        return {
            "ok": True,
            "tracks": {
                key: value.model_dump() for key, value in meta.tracks.items()
            },
        }

    @app.get("/api/v1/timelines")
    def timeline_snapshot_list() -> dict[str, object]:
        return {"ok": True, "timelines": list_snapshots()}

    @app.post("/api/v1/jobs/{job_id}/timeline/snapshots", status_code=201)
    def save_timeline_snapshot(
        job_id: str, request: TimelineSnapshotRequest
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
            state_path = _timeline_state_path(job)
            state = ProjectState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            )
            metadata = save_snapshot(state, name=request.name, job_id=job_id)
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "snapshot_failed", "message": str(exc)},
            ) from exc
        return {"ok": True, "timeline": metadata}

    @app.post("/api/v1/timelines/import", status_code=201)
    def import_timeline_snapshot(
        request: TimelineSnapshotImportRequest,
    ) -> dict[str, object]:
        try:
            metadata = import_snapshot(
                request.payload, name=request.name, job_id=request.job_id
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "snapshot_invalid", "message": str(exc)},
            ) from exc
        return {"ok": True, "timeline": metadata}

    @app.get("/api/v1/timelines/{snapshot_id}/file")
    def download_timeline_snapshot(snapshot_id: str) -> FileResponse:
        try:
            path = snapshot_path(snapshot_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "snapshot_invalid", "message": str(exc)},
            ) from exc
        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "snapshot_not_found"},
            )
        return FileResponse(path, media_type="application/json", filename=path.name)

    @app.delete("/api/v1/timelines/{snapshot_id}")
    def remove_timeline_snapshot(snapshot_id: str) -> dict[str, object]:
        try:
            removed = delete_snapshot(snapshot_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "snapshot_invalid", "message": str(exc)},
            ) from exc
        if not removed:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "snapshot_not_found"},
            )
        return {"ok": True, "removed": snapshot_id}

    @app.post("/api/v1/timelines/{snapshot_id}/load")
    def load_timeline_snapshot(
        snapshot_id: str, request: TimelineSnapshotLoadRequest
    ) -> dict[str, object]:
        try:
            job = jobs.get(request.job_id)
            _assert_tracks_unlocked(job, set())
            metadata, saved = read_snapshot(snapshot_id)
            if saved.media_info is None:
                raise StateNotReadyError("The saved timeline has no media information.")
            source = resolve_allowed(
                Path(saved.media_info.source_path), allowed_roots()
            )
            if not source.is_file():
                raise StateNotReadyError(
                    f"The saved timeline source is offline: {source}"
                )
            saved.media_info = saved.media_info.model_copy(
                update={"source_path": str(source)}
            )
            state_path = _timeline_state_path(job)
            history = _timeline_history(job)
            current = ProjectState.model_validate_json(
                state_path.read_text(encoding="utf-8")
            )
            previous = current.model_copy(deep=True)
            loaded = _apply_and_store(
                job, saved, state_path, history, current.revision + 1
            )
            history.record(previous)
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "snapshot_load_failed", "message": str(exc)},
            ) from exc
        return {
            "ok": True,
            "revision": loaded.revision,
            "snapshot": metadata,
        }

    @app.get("/api/v1/jobs/{job_id}/timeline")
    def job_timeline(
        job_id: str, request: Request, response: Response
    ) -> object:
        try:
            job = jobs.get(job_id)
            state_path = Path(
                str((job.result or {}).get("state_path") or job.output / "project_state.json")
            )
            if not state_path.is_file():
                raise StateNotReadyError("The job has no project_state.json timeline.")
            state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "timeline_invalid", "message": str(exc)},
            ) from exc
        media = state.media_info
        fps = (media.fps_num / media.fps_den) if media is not None else 30.0
        duration = max(
            (clip.timeline_out_frame for clip in state.video_segments),
            default=0,
        ) / max(0.001, fps)
        history = _timeline_history(job)
        meta = load_meta(job.output)
        broll_plan = (job.result or {}).get("broll_plan", {})
        live_eligible, live_reason = _live_playback(state, meta)
        titles, titles_ready = _live_titles(job.output)
        if live_eligible and not titles_ready:
            live_eligible, live_reason = (
                False,
                "titles require the rendered preview",
            )
        if live_eligible:
            for path in (
                job.output / "color" / "filters.json",
                job.output / "audio" / "master-filters.json",
            ):
                if read_filters(path):
                    live_eligible, live_reason = (
                        False,
                        "master filters require the rendered preview",
                    )
                    break
        etag = _timeline_etag(state.revision)
        if (request.headers.get("if-none-match") or "").strip() in {etag, "*"}:
            return Response(status_code=304, headers={"ETag": etag})
        response.headers["ETag"] = etag
        return {
            "ok": True,
            "job_id": job_id,
            "revision": state.revision,
            "can_undo": history.can_undo,
            "can_redo": history.can_redo,
            "fps": round(fps, 6),
            "duration_sec": round(duration, 3),
            "source_duration_sec": round(
                (media.duration_frames / fps) if media is not None else 0.0, 3
            ),
            "live_eligible": live_eligible,
            "live_reason": live_reason,
            "live_source": live_sources.status(
                job, height=media.height if media is not None else 0
            ).to_dict(),
            "video": [
                {
                    "id": clip.clip_id,
                    "start_sec": round(clip.timeline_in_frame / fps, 3),
                    "end_sec": round(clip.timeline_out_frame / fps, 3),
                    "source_in_frame": clip.source_in_frame,
                    "source_out_frame": clip.source_out_frame,
                    "source_start_sec": round(clip.source_in_frame / fps, 3),
                    "source_end_sec": round(clip.source_out_frame / fps, 3),
                    "zoom": clip.transform.scale,
                    "pos_x": clip.transform.pos_x,
                    "pos_y": clip.transform.pos_y,
                    "keyframes": len(clip.transform.keyframes),
                    "transition": clip.transition_out.type if clip.transition_out else None,
                    "transition_frames": (
                        clip.transition_out.duration_frames if clip.transition_out else 0
                    ),
                    "transition_audio": (
                        clip.transition_out.audio if clip.transition_out else False
                    ),
                }
                for clip in state.video_segments
            ],
            "audio": [
                {
                    "id": clip.clip_id,
                    "start_sec": round(
                        clip.timeline_in_sample / max(1, media.audio_sample_rate), 3
                    ),
                    "end_sec": round(
                        clip.timeline_out_sample / max(1, media.audio_sample_rate), 3
                    ),
                    "fade_in_sec": round(
                        clip.fade_in_samples / max(1, media.audio_sample_rate), 3
                    ),
                    "fade_out_sec": round(
                        clip.fade_out_samples / max(1, media.audio_sample_rate), 3
                    ),
                    "source_in_sec": round(
                        clip.source_in_sample / max(1, media.audio_sample_rate), 3
                    ),
                    "source_out_sec": round(
                        clip.source_out_sample / max(1, media.audio_sample_rate), 3
                    ),
                }
                for clip in state.audio_segments
            ]
            if media is not None
            else [],
            "inactive": [
                {
                    "id": item.clip_id,
                    "reason": item.reason,
                    "video_start_sec": round(item.video.source_in_frame / fps, 3),
                    "video_end_sec": round(item.video.source_out_frame / fps, 3),
                    "audio_start_sec": round(
                        item.audio.source_in_sample / max(1, media.audio_sample_rate), 3
                    ),
                    "audio_end_sec": round(
                        item.audio.source_out_sample / max(1, media.audio_sample_rate), 3
                    ),
                }
                for item in state.inactive_segments
            ]
            if media is not None
            else [],
            "captions": [
                {
                    "id": sentence.id,
                    "start_sec": round(
                        sentence.start_sample / max(1, media.audio_sample_rate), 3
                    ),
                    "end_sec": round(
                        sentence.end_sample / max(1, media.audio_sample_rate), 3
                    ),
                    "text": sentence.text,
                    "speaker": sentence.speaker,
                }
                for sentence in state.transcript
            ]
            if media is not None
            else [],
            "shorts": (job.result or {}).get("shorts", []),
            "broll": broll_plan,
            "broll_approval": load_approvals(job.output),
            "markers": [item.model_dump(mode="json") for item in meta.markers],
            "tracks": {key: value.model_dump() for key, value in meta.tracks.items()},
            "comments": [item.model_dump(mode="json") for item in meta.comments],
            "overlays": [item.model_dump(mode="json") for item in state.overlays],
            "titles": titles,
            "media": {
                "source_path": media.source_path if media is not None else "",
                "audio_sample_rate": media.audio_sample_rate if media is not None else 0,
            },
        }

    @app.get("/api/v1/jobs/{job_id}/overlays/{overlay_id}/file")
    def job_overlay_file(job_id: str, overlay_id: str) -> FileResponse:
        job = jobs.get(job_id)
        state = load_state(_timeline_state_path(job))
        overlay = next(
            (item for item in state.overlays if item.overlay_id == overlay_id),
            None,
        )
        if overlay is None:
            raise StateNotReadyError(f"Unknown overlay: {overlay_id}")
        path = resolve_allowed(Path(overlay.path), allowed_roots())
        if not path.is_file():
            raise StateNotReadyError("The overlay asset is not available.")
        return FileResponse(path, filename=path.name)

    @app.get("/api/v1/jobs/{job_id}/timeline/waveform")
    def job_waveform(
        job_id: str,
        start: float = 0.0,
        end: float | None = None,
        buckets: int = 240,
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
            state_path = Path(
                str((job.result or {}).get("state_path") or job.output / "project_state.json")
            )
            if not state_path.is_file():
                raise StateNotReadyError("The job has no project_state.json timeline.")
            state = load_state(state_path)
            media = state.media_info
            if media is None:
                raise StateNotReadyError("The project has no media info.")
            source = Path(media.source_path).expanduser()
            if not source.is_file():
                raise StateNotReadyError("The source media is not available.")
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "waveform_invalid", "message": str(exc)},
            ) from exc
        stop = end if end is not None else start + max(0.1, buckets * 0.05)
        stop = max(start + 0.01, min(stop, start + 3600.0))
        try:
            return peaks_for_range(
                source,
                start_sec=max(0.0, start),
                end_sec=stop,
                buckets=max(1, min(4096, buckets)),
            )
        except (OSError, ValueError, IngestError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "waveform_failed", "message": str(exc)},
            ) from exc
