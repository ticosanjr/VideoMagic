"""Shared state and helpers for MCP tool registration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from videoflow.application.jobs import JobManager
from videoflow.domain.errors import StateNotReadyError
from videoflow.domain.state import MediaInfo, ProjectState, Sentence
from videoflow.domain.state import ProjectState as TimelineProjectState
from videoflow.engine.batch import BatchManager


@dataclass
class ToolContext:
    """Mutable server state shared by every tool domain."""

    manager: JobManager
    batch_manager: BatchManager
    last: dict[str, Any] = field(default_factory=lambda: {"pending_options": {}})

    def timeline_job(self, job_id: str | None = None) -> Any:
        resolved = job_id or self.last.get("job_id")
        if not resolved:
            raise StateNotReadyError("No job is loaded. Run a pipeline first.")
        return self.manager.get(str(resolved))

    def state_for_job(self, job: Any) -> TimelineProjectState | None:
        path = Path(
            str((job.result or {}).get("state_path") or job.output / "project_state.json")
        )
        if not path.is_file():
            return None
        try:
            return TimelineProjectState.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return None

    def project_state(self) -> ProjectState | None:
        output = self.last.get("output")
        if not isinstance(output, Path):
            return None
        path = output / "project_state.json"
        if not path.is_file():
            return None
        try:
            return ProjectState.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def transcript_for(self) -> list[Sentence] | None:
        cached = self.last.get("transcript")
        if (
            isinstance(cached, list)
            and cached
            and all(isinstance(item, Sentence) for item in cached)
        ):
            return cached
        state = self.project_state()
        if state is not None and state.transcript:
            return state.transcript
        return None

    def sample_rate(self, state: ProjectState | None) -> int:
        if state is not None and state.media_info is not None:
            return state.media_info.audio_sample_rate
        media = self.last.get("media")
        if isinstance(media, MediaInfo):
            return media.audio_sample_rate
        return 48000


def error(code: str, message: str) -> dict[str, object]:
    return {"ok": False, "code": code, "message": message}


def source_required() -> dict[str, object]:
    return error(
        "source_required",
        "Call videoflow_load_media first or pass source to a recipe run.",
    )


def sentences_payload(
    sentences: list[Sentence], *, include_words: bool
) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for sentence in sentences:
        item: dict[str, object] = {
            "id": sentence.id,
            "start_sample": sentence.start_sample,
            "end_sample": sentence.end_sample,
            "text": sentence.text,
        }
        if include_words:
            item["words"] = [word.model_dump(mode="json") for word in sentence.words]
        payload.append(item)
    return payload
