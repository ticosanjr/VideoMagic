"""Deterministic beat-map draft from the transcript and one style."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.domain.state import ProjectState


class TimeRangeSec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(gt=0.0)


class BeatMapPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    style_id: str = ""
    time_basis: Literal["edited", "source"] = "edited"
    keep_ranges: list[TimeRangeSec] = Field(default_factory=list)
    remove_ranges: list[TimeRangeSec] = Field(default_factory=list)
    overlays: list[dict[str, Any]] = Field(default_factory=list)
    transitions: list[dict[str, Any]] = Field(default_factory=list)
    captions: list[dict[str, Any]] = Field(default_factory=list)
    instructions: str = ""
    warnings: list[str] = Field(default_factory=list)


def build_beatmap_plan(
    state: ProjectState,
    style: Any,
    *,
    instructions: str = "",
) -> dict[str, Any]:
    """Build a non-destructive plan; callers decide whether to apply it."""

    media = state.media_info
    if media is None:
        return BeatMapPlan(
            style_id=getattr(style, "style_id", ""),
            instructions=instructions,
            warnings=["project has no media"],
        ).model_dump(mode="json")
    fps = media.fps_num / media.fps_den
    discard = set(state.pipeline.discard_sentence_ids)
    sentences = [item for item in state.transcript if item.id not in discard]
    captions: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    for sentence in sentences:
        start = max(0, round(sentence.start_sample / media.audio_sample_rate * fps))
        end = max(start + 1, round(sentence.end_sample / media.audio_sample_rate * fps))
        captions.append(
            {
                "text": sentence.text,
                "start_frame": start,
                "end_frame": end,
                "preset": getattr(style, "caption_preset", ""),
            }
        )
    for clip in sorted(state.video_segments, key=lambda item: item.timeline_in_frame)[:-1]:
        if clip.transition_out is None:
            transitions.append(
                {
                    "clip_id": clip.clip_id,
                    "type": "crossfade",
                    "duration_frames": 6,
                    "audio": True,
                    "linked_sfx": "",
                }
            )
    return BeatMapPlan(
        style_id=getattr(style, "style_id", ""),
        instructions=instructions,
        captions=captions,
        transitions=transitions,
    ).model_dump(mode="json")


def write_beatmap_plan(output: Path, plan: dict[str, Any]) -> Path:
    import json

    target = Path(output).expanduser() / "beat_map.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


__all__ = ["BeatMapPlan", "TimeRangeSec", "build_beatmap_plan", "write_beatmap_plan"]
