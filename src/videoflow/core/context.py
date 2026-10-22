"""Shared, typed state for one recipe run.

The context carries artifact *references* and hashes, never raw media. Steps
mutate the context in dependency order; the recipe runner owns persistence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.domain.state import ManualOverride, MediaInfo, ProjectState, Sentence
from videoflow.domain.timebase import Rounding


class PipelineContext(BaseModel):
    """State passed between recipe steps."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: Path
    output: Path
    work: Path
    exports: Path

    media: MediaInfo | None = None
    pcm_path: Path | None = None
    pcm_digest: str = ""
    speech_intervals: list[tuple[int, int]] = Field(default_factory=list)
    vad_engine: str = "none"
    transcript: list[Sentence] = Field(default_factory=list)
    transcript_source: str = "none"
    discard_sentence_ids: list[int] = Field(default_factory=list)
    restored_sentence_ids: list[int] = Field(default_factory=list)
    manual_overrides: list[ManualOverride] = Field(default_factory=list)
    state: ProjectState | None = None
    shorts: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    hashes: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    selected_shorts: list[Any] = Field(default_factory=list, exclude=True, repr=False)

    def duration_samples(self) -> int:
        if self.media is None:
            return 0
        timebase = self.media.timebase()
        return timebase.seconds_to_samples(
            timebase.frames_to_seconds(self.media.duration_frames),
            Rounding.NEAREST,
        )

    def summary(self) -> dict[str, Any]:
        """Small, JSON-safe view for API responses and reports."""

        media = self.media
        return {
            "source": str(self.source),
            "output": str(self.output),
            "media": media.model_dump(mode="json") if media is not None else None,
            "speech_interval_count": len(self.speech_intervals),
            "vad_engine": self.vad_engine,
            "transcript_sentence_count": len(self.transcript),
            "transcript_source": self.transcript_source,
            "video_segment_count": len(self.state.video_segments) if self.state else 0,
            "audio_segment_count": len(self.state.audio_segments) if self.state else 0,
            "short_count": len(self.shorts),
            "warnings": list(self.warnings),
            "artifacts": dict(self.artifacts),
            "hashes": dict(self.hashes),
        }
