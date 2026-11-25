"""Deterministic beat-map draft from the transcript and one style."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.spans import merge_spans
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
    keep_ranges: list[TimeRangeSec] = []
    remove_ranges: list[TimeRangeSec] = []
    source_fps = media.fps_num / media.fps_den
    if state.video_segments:
        keep_ranges = [
            TimeRangeSec(
                start_sec=round(clip.source_in_frame / source_fps, 6),
                end_sec=round(max(clip.source_in_frame + 1, clip.source_out_frame) / source_fps, 6),
            )
            for clip in sorted(state.video_segments, key=lambda item: item.timeline_in_frame)
        ]
    if state.inactive_segments:
        rate = media.audio_sample_rate
        remove_ranges = [
            TimeRangeSec(
                start_sec=round(segment.audio.source_in_sample / rate, 6),
                end_sec=round(
                    max(
                        segment.audio.source_in_sample + 1,
                        segment.audio.source_out_sample,
                    )
                    / rate,
                    6,
                ),
            )
            for segment in state.inactive_segments
        ]
    if not keep_ranges and not remove_ranges:
        rate = media.audio_sample_rate
        duration_samples = max(
            1,
            round(media.duration_frames * rate * media.fps_den / media.fps_num),
        )
        source_spans: list[tuple[int, int]] = []
        raw_safe = state.pipeline.metadata.get("decupage_safe_spans")
        if isinstance(raw_safe, list):
            for item in raw_safe:
                try:
                    start, end = int(item[0]), int(item[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if end > start:
                    source_spans.append((max(0, start), min(duration_samples, end)))
        if not source_spans and state.vad_intervals:
            source_spans = [
                (max(0, item.start_sample), min(duration_samples, item.end_sample))
                for item in state.vad_intervals
                if item.end_sample > item.start_sample
            ]
        if source_spans:
            kept = merge_spans(source_spans)
            keep_ranges = [
                TimeRangeSec(
                    start_sec=round(start / rate, 6),
                    end_sec=round(min(duration_samples, end) / rate, 6),
                )
                for start, end in kept
                if end > start
            ]
            cursor = 0
            for start, end in kept:
                if start > cursor:
                    remove_ranges.append(
                        TimeRangeSec(
                            start_sec=round(cursor / rate, 6),
                            end_sec=round(start / rate, 6),
                        )
                    )
                cursor = max(cursor, end)
            if cursor < duration_samples:
                remove_ranges.append(
                    TimeRangeSec(
                        start_sec=round(cursor / rate, 6),
                        end_sec=round(duration_samples / rate, 6),
                    )
                )
    return BeatMapPlan(
        style_id=getattr(style, "style_id", ""),
        time_basis="source" if keep_ranges or remove_ranges else "edited",
        instructions=instructions,
        captions=captions,
        transitions=transitions,
        keep_ranges=keep_ranges,
        remove_ranges=remove_ranges,
    ).model_dump(mode="json")


def write_beatmap_plan(output: Path, plan: dict[str, Any]) -> Path:
    import json

    target = Path(output).expanduser() / "beat_map.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


__all__ = ["BeatMapPlan", "TimeRangeSec", "build_beatmap_plan", "write_beatmap_plan"]
