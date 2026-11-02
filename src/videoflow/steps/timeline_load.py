"""Load a saved timeline snapshot into a recipe."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videoflow.application.timeline_snapshots import (
    read_snapshot,
    read_snapshot_file,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class TimelineLoadParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(default="", max_length=4000)
    snapshot_id: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def require_source(self) -> TimelineLoadParams:
        if not self.path.strip() and not self.snapshot_id.strip():
            raise ValueError("Provide a timeline path or snapshot_id")
        return self


@register_step
class TimelineLoadStep(BaseStep):
    type = "timeline.load"
    title = "Load timeline"
    description = "Load a saved timeline snapshot and pass it to export or render nodes."
    requires = ()
    produces = ("timeline", "media")
    params_model = TimelineLoadParams
    icon = "folder"
    color = "#f59e0b"

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = TimelineLoadParams.model_validate(params)
        io.report(20, "Reading the saved timeline")
        try:
            if options.snapshot_id.strip():
                metadata, state = read_snapshot(options.snapshot_id.strip())
            else:
                path = resolve_allowed(Path(options.path), allowed_roots())
                metadata, state = read_snapshot_file(path)
        except (OSError, ValueError) as exc:
            raise IngestError(f"Cannot load the saved timeline: {exc}") from exc
        media = state.media_info
        if media is None:
            raise IngestError("The saved timeline has no media information.")
        source = resolve_allowed(Path(media.source_path), allowed_roots())
        if not source.is_file():
            raise IngestError(f"The saved timeline source is offline: {source}")
        context.source = source
        context.media = media.model_copy(update={"source_path": str(source)})
        context.state = state
        context.transcript = list(state.transcript)
        context.metadata["timeline_snapshot"] = metadata
        context.hashes["timeline.load"] = digest_payload(metadata)
        io.report(100, f"Loaded {metadata.get('name') or 'timeline'}")
