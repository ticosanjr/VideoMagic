"""Atomic declarative timeline edits for one MCP call.

A beatmap carries cuts, B-roll/overlays, zoom keyframes, SFX and music. The
whole manifest is validated against a project copy and persisted once, so a
partial failure never leaves the timeline half-edited.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videoflow.application.asset_providers import license_blockers
from videoflow.application.captions import CaptionLine, build_ass_lines
from videoflow.domain.state import (
    AudioSegment,
    OverlayClip,
    ProjectState,
    TransformKeyframe,
    Transition,
    VideoSegment,
)


class BeatmapCut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> BeatmapCut:
        if self.end_frame <= self.start_frame:
            raise ValueError("cut end_frame must be greater than start_frame")
        return self


class BeatmapOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    kind: Literal["image", "video"] = "video"
    overlay_id: str = ""
    width_ratio: float = Field(default=1.0, gt=0.0, le=1.0)
    position_x: float = Field(default=0.5, ge=0.0, le=1.0)
    position_y: float = Field(default=0.5, ge=0.0, le=1.0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    layout: Literal[
        "fullscreen",
        "pip_top_right",
        "split_screen",
        "cutout_overlay",
        "ken_burns",
        "transformative_crop",
    ] = "fullscreen"
    ken_burns: bool = False
    transformative_crop: bool = False


class BeatmapTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clip_id: str = Field(min_length=1)
    type: Literal[
        "crossfade",
        "fade_to_black",
        "wipe_left",
        "wipe_right",
        "slide_up",
        "zoom_in",
        "whip_pan",
        "glitch",
    ] = "crossfade"
    duration_frames: int = Field(default=6, ge=1, le=120)
    audio: bool = True
    linked_sfx: str = ""


class BeatmapGraphic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    engine: str = ""
    alpha: bool = True
    position_x: float = Field(default=0.5, ge=0.0, le=1.0)
    position_y: float = Field(default=0.5, ge=0.0, le=1.0)
    width_ratio: float = Field(default=0.6, gt=0.0, le=1.0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class BeatmapCaption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    preset: str = ""
    safe_zone: str = ""


class BeatmapZoom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clip_id: str = Field(min_length=1)
    keyframes: list[TransformKeyframe] = Field(default_factory=list)


class BeatmapSfx(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(default=0, ge=0)
    gain_db: float = Field(default=0.0, ge=-60.0, le=12.0)


class BeatmapMusic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    start_frame: int = Field(default=0, ge=0)
    end_frame: int = Field(default=0, ge=0)
    gain_db: float = Field(default=-18.0, ge=-60.0, le=12.0)
    duck_under_speech: bool = True


class Beatmap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int | None = Field(default=None, ge=1)
    cuts: list[BeatmapCut] = Field(default_factory=list)
    broll: list[BeatmapOverlay] = Field(default_factory=list)
    overlays: list[BeatmapOverlay] = Field(default_factory=list)
    zoom_keyframes: list[BeatmapZoom] = Field(default_factory=list)
    sfx_events: list[BeatmapSfx] = Field(default_factory=list)
    music_tracks: list[BeatmapMusic] = Field(default_factory=list)
    transitions: list[BeatmapTransition] = Field(default_factory=list)
    graphics: list[BeatmapGraphic] = Field(default_factory=list)
    captions: list[BeatmapCaption] = Field(default_factory=list)


@dataclass(slots=True)
class BeatmapReport:
    ok: bool = True
    cuts: int = 0
    overlays: int = 0
    zooms: int = 0
    sfx_events: int = 0
    music_tracks: int = 0
    transitions: int = 0
    graphics: int = 0
    captions: int = 0
    conflicts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "cuts": self.cuts,
            "overlays": self.overlays,
            "zooms": self.zooms,
            "sfx_events": self.sfx_events,
            "music_tracks": self.music_tracks,
            "transitions": self.transitions,
            "graphics": self.graphics,
            "captions": self.captions,
            "conflicts": list(self.conflicts),
            "warnings": list(self.warnings),
        }


class BeatmapError(ValueError):
    """Raised when the beatmap cannot be applied atomically."""

    def __init__(self, message: str, *, report: BeatmapReport | None = None) -> None:
        super().__init__(message)
        self.report = report or BeatmapReport(ok=False)


def _blocked(output: Path) -> set[str]:
    blocked: set[str] = set()
    for item in license_blockers(output):
        for key in ("path", "title", "local_path"):
            value = str(item.get(key) or "").strip()
            if value:
                blocked.add(str(Path(value).expanduser()))
                blocked.add(Path(value).name)
    return blocked


def _resolve_asset(value: str, output: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(output) / path
    return path


def _validate_asset(value: str, output: Path, blocked: set[str], report: BeatmapReport) -> Path:
    path = _resolve_asset(value, output)
    if not path.is_file():
        report.conflicts.append(f"missing asset: {value}")
        return path
    if str(path) in blocked or path.name in blocked:
        report.conflicts.append(f"license-blocked asset: {value}")
    return path


def _cut_video(
    segments: list[VideoSegment],
    cuts: list[BeatmapCut],
) -> list[VideoSegment]:
    result: list[VideoSegment] = []
    cursor = 0
    for clip in sorted(segments, key=lambda item: item.timeline_in_frame):
        pieces: list[tuple[int, int]] = []
        for cut in cuts:
            start = max(clip.timeline_in_frame, cut.start_frame)
            end = min(clip.timeline_out_frame, cut.end_frame)
            if end > start:
                pieces.append((start, end))
        for piece_index, (start, end) in enumerate(pieces):
            source_in = clip.source_in_frame + (start - clip.timeline_in_frame)
            source_out = source_in + (end - start)
            is_last_piece = piece_index == len(pieces) - 1
            transition = (
                clip.transition_out if is_last_piece and end == clip.timeline_out_frame else None
            )
            result.append(
                clip.model_copy(
                    update={
                        "clip_id": f"{clip.clip_id}-cut{piece_index + 1}",
                        "source_in_frame": source_in,
                        "source_out_frame": source_out,
                        "timeline_in_frame": cursor,
                        "timeline_out_frame": cursor + (end - start),
                        "transition_out": transition,
                    }
                )
            )
            cursor += end - start
    return result


def _cut_audio(
    segments: list[AudioSegment],
    cuts: list[BeatmapCut],
    media_fps: tuple[int, int],
    sample_rate: int,
) -> list[AudioSegment]:
    fps_num, fps_den = media_fps

    def to_sample(frame: int) -> int:
        return round(frame * fps_den * sample_rate / fps_num)

    result: list[AudioSegment] = []
    cursor = 0
    for clip in sorted(segments, key=lambda item: item.timeline_in_sample):
        start_sample = clip.timeline_in_sample
        end_sample = clip.timeline_out_sample
        pieces: list[tuple[int, int]] = []
        for cut in cuts:
            start = max(start_sample, to_sample(cut.start_frame))
            end = min(end_sample, to_sample(cut.end_frame))
            if end > start:
                pieces.append((start, end))
        for piece_index, (start, end) in enumerate(pieces):
            source_in = clip.source_in_sample + (start - start_sample)
            source_out = source_in + (end - start)
            result.append(
                clip.model_copy(
                    update={
                        "clip_id": f"{clip.clip_id}-cut{piece_index + 1}",
                        "source_in_sample": source_in,
                        "source_out_sample": source_out,
                        "timeline_in_sample": cursor,
                        "timeline_out_sample": cursor + (end - start),
                    }
                )
            )
            cursor += end - start
    return result


def _overlay_from(entry: BeatmapOverlay, index: int, path: Path) -> OverlayClip:
    width, x, y = entry.width_ratio, entry.position_x, entry.position_y
    if entry.layout == "pip_top_right":
        width, x, y = 0.32, 0.82, 0.18
    elif entry.layout == "split_screen":
        width, x, y = 1.0, 0.5, 0.25
    elif entry.layout == "cutout_overlay":
        width, x, y = 0.6, 0.5, 0.72
    elif entry.layout in {"ken_burns", "transformative_crop"}:
        width, x, y = max(0.75, width), 0.5, 0.5
    return OverlayClip(
        overlay_id=entry.overlay_id or f"beatmap-{index + 1}",
        path=str(path),
        start_frame=entry.start_frame,
        duration_frames=entry.duration_frames,
        position_x=x,
        position_y=y,
        width_ratio=width,
        opacity=entry.opacity,
        kind=entry.kind,
    )


def apply_beatmap(
    state: ProjectState,
    output: Path,
    beatmap: Beatmap | dict[str, Any],
    *,
    expected_revision: int | None = None,
) -> tuple[ProjectState, BeatmapReport, dict[str, Any]]:
    """Apply a beatmap and return ``(new_state, report, sidecar_manifest)``."""

    options = beatmap if isinstance(beatmap, Beatmap) else Beatmap.model_validate(beatmap)
    report = BeatmapReport()
    output = Path(output).expanduser()
    if expected_revision is None:
        expected_revision = options.revision
    if expected_revision is not None and state.revision != expected_revision:
        report.ok = False
        report.conflicts.append(
            f"revision conflict: expected {expected_revision}, current {state.revision}"
        )
        raise BeatmapError("revision conflict", report=report)
    if state.media_info is None:
        report.ok = False
        report.conflicts.append("project has no media")
        raise BeatmapError("project has no media", report=report)

    blocked = _blocked(output)
    updates: dict[str, Any] = {}

    if options.cuts:
        duration = max((clip.timeline_out_frame for clip in state.video_segments), default=0)
        for cut in options.cuts:
            if cut.end_frame > duration:
                report.conflicts.append(
                    f"cut {cut.start_frame}-{cut.end_frame} exceeds timeline {duration}"
                )
        ordered = sorted(options.cuts, key=lambda item: item.start_frame)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.start_frame < previous.end_frame:
                report.conflicts.append(
                    f"overlapping cuts {previous.start_frame}-{previous.end_frame} "
                    f"and {current.start_frame}-{current.end_frame}"
                )
        if not report.conflicts:
            media = state.media_info
            updates["video_segments"] = _cut_video(state.video_segments, ordered)
            updates["audio_segments"] = _cut_audio(
                state.audio_segments,
                ordered,
                (media.fps_num, media.fps_den),
                media.audio_sample_rate,
            )
            report.cuts = len(ordered)

    overlays = list(state.overlays)
    for entry in [*options.broll, *options.overlays]:
        path = _validate_asset(entry.path, output, blocked, report)
        if path.is_file():
            overlays.append(_overlay_from(entry, len(overlays), path))
    if report.conflicts:
        report.ok = False
        raise BeatmapError("; ".join(report.conflicts), report=report)
    updates["overlays"] = overlays
    report.overlays = len(options.broll) + len(options.overlays)

    if options.zoom_keyframes:
        source_ids = {clip.clip_id for clip in state.video_segments}
        working = list(updates.get("video_segments", state.video_segments))
        missing = [
            zoom.clip_id
            for zoom in options.zoom_keyframes
            if zoom.clip_id not in source_ids
            and not any(clip.clip_id.startswith(f"{zoom.clip_id}-cut") for clip in working)
        ]
        if missing:
            report.conflicts.extend(f"unknown clip for zoom: {clip_id}" for clip_id in missing)
            report.ok = False
            raise BeatmapError("; ".join(report.conflicts), report=report)
        segments = []
        for clip in working:
            target = next(
                (
                    zoom
                    for zoom in options.zoom_keyframes
                    if clip.clip_id == zoom.clip_id
                    or clip.clip_id.startswith(f"{zoom.clip_id}-cut")
                ),
                None,
            )
            if target is None:
                segments.append(clip)
                continue
            segments.append(
                clip.model_copy(
                    update={
                        "transform": clip.transform.model_copy(
                            update={"keyframes": target.keyframes}
                        )
                    }
                )
            )
        updates["video_segments"] = segments
        report.zooms = len(options.zoom_keyframes)

    if options.transitions:
        working = list(updates.get("video_segments", state.video_segments))
        for item in options.transitions:
            matches = [
                clip
                for clip in working
                if clip.clip_id == item.clip_id or clip.clip_id.startswith(f"{item.clip_id}-cut")
            ]
            if not matches:
                report.conflicts.append(f"unknown clip for transition: {item.clip_id}")
                continue
            target = sorted(matches, key=lambda clip: clip.timeline_in_frame)[-1]
            updated_clip = target.model_copy(
                update={
                    "transition_out": Transition(
                        type=item.type,
                        duration_frames=item.duration_frames,
                        audio=item.audio,
                    )
                }
            )
            working = [updated_clip if clip.clip_id == target.clip_id else clip for clip in working]
        updates["video_segments"] = working
        report.transitions = len(options.transitions)

    if options.graphics:
        overlays = list(updates.get("overlays", state.overlays))
        for entry in options.graphics:
            path = _validate_asset(entry.path, output, blocked, report)
            if not path.is_file():
                continue
            overlays.append(
                OverlayClip(
                    overlay_id=f"graphic-{len(overlays) + 1}",
                    path=str(path),
                    start_frame=entry.start_frame,
                    duration_frames=entry.duration_frames,
                    position_x=entry.position_x,
                    position_y=entry.position_y,
                    width_ratio=entry.width_ratio,
                    opacity=entry.opacity,
                    kind="image",
                )
            )
        updates["overlays"] = overlays
        report.graphics = len(options.graphics)

    if report.conflicts:
        report.ok = False
        raise BeatmapError("; ".join(report.conflicts), report=report)

    sidecar: dict[str, Any] = {
        "schema_version": 2,
        "transitions": [item.model_dump(mode="json") for item in options.transitions],
        "graphics": [item.model_dump(mode="json") for item in options.graphics],
        "captions": [item.model_dump(mode="json") for item in options.captions],
        "sfx_events": [],
        "music_tracks": [],
    }
    for cue in options.sfx_events:
        path = _validate_asset(cue.path, output, blocked, report)
        if path.is_file():
            sidecar["sfx_events"].append(
                {
                    "path": str(path),
                    "start_frame": cue.start_frame,
                    "duration_frames": cue.duration_frames,
                    "gain_db": cue.gain_db,
                }
            )
    for transition in options.transitions:
        if not transition.linked_sfx:
            continue
        path = _validate_asset(transition.linked_sfx, output, blocked, report)
        if path.is_file():
            matches = [
                clip
                for clip in updates.get("video_segments", state.video_segments)
                if clip.clip_id == transition.clip_id
                or clip.clip_id.startswith(f"{transition.clip_id}-cut")
            ]
            target = (
                sorted(matches, key=lambda clip: clip.timeline_in_frame)[-1] if matches else None
            )
            start = (
                max(0, target.timeline_out_frame - transition.duration_frames)
                if target is not None
                else 0
            )
            sidecar["sfx_events"].append(
                {
                    "path": str(path),
                    "start_frame": start,
                    "duration_frames": transition.duration_frames,
                    "gain_db": 0.0,
                    "linked_transition": transition.type,
                }
            )
    for track in options.music_tracks:
        path = _validate_asset(track.path, output, blocked, report)
        if path.is_file():
            sidecar["music_tracks"].append(
                {
                    "path": str(path),
                    "start_frame": track.start_frame,
                    "end_frame": track.end_frame,
                    "gain_db": track.gain_db,
                    "duck_under_speech": track.duck_under_speech,
                }
            )
    report.sfx_events = len(sidecar["sfx_events"])
    report.music_tracks = len(sidecar["music_tracks"])
    if report.conflicts:
        report.ok = False
        raise BeatmapError("; ".join(report.conflicts), report=report)

    if options.captions:
        fps = state.media_info.fps_num / state.media_info.fps_den
        lines = [
            CaptionLine(
                start=item.start_frame / max(1e-9, fps),
                end=item.end_frame / max(1e-9, fps),
                text=item.text,
            )
            for item in options.captions
            if item.end_frame > item.start_frame
        ]
        directory = output / "captions"
        directory.mkdir(parents=True, exist_ok=True)
        captions_path = directory / "beatmap.ass"
        captions_path.write_text(build_ass_lines(lines, width=1920, height=1080), encoding="utf-8")
        subtitles = output / "subtitles.ass"
        if not subtitles.exists():
            shutil.copy2(captions_path, subtitles)
        sidecar["captions_file"] = str(captions_path)
        report.captions = len(lines)

    updated = state.model_copy(update=updates)
    return updated, report, sidecar


def write_beatmap_sidecar(output: Path, manifest: dict[str, Any]) -> Path:
    path = Path(output) / "audio" / "beatmap.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


__all__ = [
    "Beatmap",
    "BeatmapCut",
    "BeatmapError",
    "BeatmapMusic",
    "BeatmapOverlay",
    "BeatmapReport",
    "BeatmapSfx",
    "BeatmapZoom",
    "apply_beatmap",
    "write_beatmap_sidecar",
]
