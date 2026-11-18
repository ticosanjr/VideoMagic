"""Deterministic beat-map draft from the transcript and one style."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.domain.state import ProjectState


def build_beatmap_plan(
    state: ProjectState,
    style: Any,
    *,
    instructions: str = "",
) -> dict[str, Any]:
    """Build a non-destructive plan; callers decide whether to apply it."""

    media = state.media_info
    if media is None:
        return {
            "schema_version": 1,
            "style_id": getattr(style, "style_id", ""),
            "instructions": instructions,
            "captions": [],
            "transitions": [],
            "zoom_keyframes": [],
            "warnings": ["project has no media"],
        }
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
    return {
        "schema_version": 1,
        "style_id": getattr(style, "style_id", ""),
        "instructions": instructions,
        "max_static_sec": getattr(style, "max_static_sec", 4.0),
        "min_silence_ms": getattr(style, "min_silence_ms", 400),
        "captions": captions,
        "transitions": transitions,
        "zoom_keyframes": [],
        "sfx_events": [],
        "music_tracks": [],
        "warnings": [],
    }


def write_beatmap_plan(output: Path, plan: dict[str, Any]) -> Path:
    import json

    target = Path(output).expanduser() / "beat_map.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


__all__ = ["build_beatmap_plan", "write_beatmap_plan"]
