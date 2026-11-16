"""Shared project, job, and resource helpers for agent MCP tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from videoflow.application import artifacts as artifact_service
from videoflow.application.projects import (
    ProjectRecord,
    get_project,
    load_project_state,
    save_project_state,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import StateNotReadyError, VideoFlowError
from videoflow.domain.state import ProjectState


def _summary(state: ProjectState | None) -> dict[str, Any]:
    if state is None:
        return {}
    media = state.media_info
    return {
        "project_id": str(state.project_id),
        "revision": state.revision,
        "sources": [
            {
                "source_id": source_id,
                "path": info.source_path,
                "duration_frames": info.duration_frames,
                "fps_num": info.fps_num,
                "fps_den": info.fps_den,
                "width": info.width,
                "height": info.height,
                "audio_sample_rate": info.audio_sample_rate,
            }
            for source_id, info in state.sources.items()
        ],
        "primary_source_id": state.primary_source_id,
        "media": media.model_dump(mode="json") if media is not None else None,
        "video_segments": len(state.video_segments),
        "audio_segments": len(state.audio_segments),
        "transcript_sentences": len(state.transcript),
        "overlays": len(state.overlays),
    }


def _record(project_id: str) -> ProjectRecord:
    return get_project(project_id)


def _state(record: ProjectRecord) -> ProjectState | None:
    try:
        return load_project_state(record)
    except StateNotReadyError:
        return None


def _job(manager: Any, project_id: str, job_id: str = "") -> Any:
    record = _record(project_id)
    if job_id:
        job = manager.get(job_id)
        if not _job_belongs(job, record):
            raise StateNotReadyError(f"Job {job_id} does not belong to project {project_id}")
        return job
    candidates = [job for job in manager.list() if _job_belongs(job, record)]
    if not candidates:
        raise StateNotReadyError("Project has no jobs yet")
    candidates.sort(key=lambda item: item.created_at, reverse=True)
    return candidates[0]


def _job_belongs(job: Any, record: ProjectRecord) -> bool:
    if getattr(job, "project_id", "") == record.project_id:
        return True
    try:
        return Path(job.output).expanduser().resolve() == Path(record.output).expanduser().resolve()
    except OSError:
        return False


def _context(record: ProjectRecord, job: Any) -> PipelineContext:
    output = Path(job.output).expanduser()
    state = _state(record)
    return PipelineContext(
        source=Path(str(job.source)).expanduser(),
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=state.media_info if state is not None else None,
        state=state,
        transcript=list(state.transcript) if state is not None else [],
        artifacts=dict((job.result or {}).get("artifacts", {})),
        metadata={"project_id": record.project_id},
    )


def _job_payload(job: Any) -> dict[str, Any]:
    payload = job.to_dict()
    payload["artifacts"] = artifact_service.list_artifacts(Path(job.output), include_hash=False)
    qa = artifact_service.qa_artifacts(Path(job.output))
    if qa["defects"]:
        payload["qa"] = {
            "defects": qa["defects"],
            "passed": False,
            "frame_count": len(qa["frames"]),
        }
    return payload


def _resources(project_id: str) -> dict[str, str]:
    return {
        "state": f"vf://projects/{project_id}/state",
        "timeline": f"vf://projects/{project_id}/timeline",
        "transcript": f"vf://projects/{project_id}/transcript",
        "jobs": f"vf://projects/{project_id}/jobs",
        "artifacts": f"vf://projects/{project_id}/artifacts",
    }


def _adopt_job(record: ProjectRecord, job: Any) -> None:
    """Attach the job output state to the project and preserve sources."""

    path = Path(job.output) / "project_state.json"
    if not path.is_file():
        return
    try:
        state = ProjectState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    previous = _state(record)
    if previous is not None and previous.sources:
        for source_id, media in previous.sources.items():
            state.add_source(source_id, media)
        state.primary_source_id = previous.primary_source_id or state.primary_source_id
        state.media_info = state.sources.get(state.primary_source_id) or state.media_info
    try:
        state = state.model_copy(update={"project_id": UUID(record.project_id)})
        save_project_state(record, state, bump_revision=False)
    except (ValueError, VideoFlowError):
        return
