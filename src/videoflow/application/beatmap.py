"""Atomic declarative timeline edits for one MCP call.

A beatmap carries cuts, B-roll/overlays, zoom keyframes, SFX and music. The
whole manifest is validated against a project copy and persisted once, so a
partial failure never leaves the timeline half-edited.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videoflow.application.captions import CaptionLine, build_ass_lines
from videoflow.application.time_map import refresh_time_map, source_range_to_timeline
from videoflow.domain.state import (
    AudioSegment,
    OverlayClip,
    ProjectState,
    TransformKeyframe,
    Transition,
    VideoSegment,
)
from videoflow.domain.timebase import Rounding
from videoflow.domains.media import license_blockers
from videoflow.domains.media.ledger import is_asset_approved


class BeatmapCut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> BeatmapCut:
        if self.end_frame <= self.start_frame:
            raise ValueError("cut end_frame must be greater than start_frame")
        return self


class BeatmapRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(gt=0.0)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end_sec <= self.start_sec:
            raise ValueError("range end_sec must be greater than start_sec")
        return self


class BeatmapOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    kind: Literal["image", "video"] = "video"
    overlay_id: str = ""
    width_ratio: float = Field(default=1.0, gt=0.0, le=1.0)
    anchor: str = "top_center"
    margin_x: int = Field(default=0, ge=0)
    margin_y: int = Field(default=0, ge=0)
    z: int = Field(default=20, ge=0, le=1000)
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
    anchor: str = "top_center"
    margin_x: int = Field(default=0, ge=0)
    margin_y: int = Field(default=0, ge=0)
    width_ratio: float = Field(default=0.6, gt=0.0, le=1.0)
    z: int = Field(default=20, ge=0, le=1000)
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

    schema_version: Literal[2] = 2
    style_id: str = ""
    instructions: str = ""
    warnings: list[str] = Field(default_factory=list)
    max_static_sec: float | None = None
    min_silence_ms: int | None = None
    revision: int | None = Field(default=None, ge=1)
    time_basis: Literal["edited", "timeline", "source"] = "timeline"
    keep_ranges: list[BeatmapRange] = Field(default_factory=list)
    remove_ranges: list[BeatmapRange] = Field(default_factory=list)
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
    before_duration_sec: float = 0.0
    after_duration_sec: float = 0.0
    delta_sec: float = 0.0
    delta_pct: float = 0.0
    affected_clips: int = 0
    dry_run: bool = False
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
            "before_duration_sec": round(self.before_duration_sec, 3),
            "after_duration_sec": round(self.after_duration_sec, 3),
            "delta_sec": round(self.delta_sec, 3),
            "delta_pct": round(self.delta_pct, 3),
            "affected_clips": self.affected_clips,
            "dry_run": self.dry_run,
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
    if (str(path) in blocked or path.name in blocked) and not is_asset_approved(
        output, path.name, path=str(path)
    ):
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
    width = entry.width_ratio
    anchor = entry.anchor
    margin_x = entry.margin_x
    margin_y = entry.margin_y
    z = entry.z
    if entry.layout == "pip_top_right":
        width, anchor, margin_x, margin_y, z = 0.32, "top_right", 32, 32, 30
    elif entry.layout == "split_screen":
        width, anchor, margin_x, margin_y, z = 1.0, "top_center", 0, 0, 10
    elif entry.layout == "cutout_overlay":
        width, anchor, margin_x, margin_y, z = 0.6, "bottom_center", 0, 80, 20
    elif entry.layout in {"ken_burns", "transformative_crop"}:
        width, anchor, margin_x, margin_y, z = max(0.75, width), "center", 0, 0, 10
    return OverlayClip(
        overlay_id=entry.overlay_id or f"beatmap-{index + 1}",
        path=str(path),
        start_frame=entry.start_frame,
        duration_frames=entry.duration_frames,
        anchor=anchor,  # type: ignore[arg-type]
        margin_x=margin_x,
        margin_y=margin_y,
        z=z,
        width_ratio=width,
        opacity=entry.opacity,
        kind=entry.kind,
        layout=entry.layout,
        ken_burns=entry.ken_burns,
        transformative_crop=entry.transformative_crop,
    )


def _timeline_duration_frames(state: ProjectState) -> int:
    return max((clip.timeline_out_frame for clip in state.video_segments), default=0)


def _seconds_to_frames(state: ProjectState, seconds: float) -> tuple[int, int]:
    media = state.media_info
    if media is None:
        return 0, 0
    timebase = media.timebase()
    value = Fraction(str(max(0.0, seconds))).limit_denominator(1_000_000)
    start = timebase.seconds_to_frames(value, Rounding.FLOOR)
    end = timebase.seconds_to_frames(value, Rounding.CEIL)
    return start, end


def _ranges_to_frames(
    state: ProjectState,
    ranges: list[BeatmapRange],
    basis: str,
) -> list[BeatmapCut]:
    cuts: list[BeatmapCut] = []
    for item in ranges:
        if basis == "source":
            for start_sec, end_sec in source_range_to_timeline(state, item.start_sec, item.end_sec):
                media = state.media_info
                if media is None:
                    continue
                timebase = media.timebase()
                start = timebase.seconds_to_frames(
                    Fraction(str(start_sec)).limit_denominator(1_000_000), Rounding.FLOOR
                )
                end = timebase.seconds_to_frames(
                    Fraction(str(end_sec)).limit_denominator(1_000_000), Rounding.CEIL
                )
                if end > start:
                    cuts.append(BeatmapCut(start_frame=start, end_frame=end))
        else:
            media = state.media_info
            if media is None:
                continue
            timebase = media.timebase()
            start = timebase.seconds_to_frames(
                Fraction(str(item.start_sec)).limit_denominator(1_000_000), Rounding.FLOOR
            )
            end = timebase.seconds_to_frames(
                Fraction(str(item.end_sec)).limit_denominator(1_000_000), Rounding.CEIL
            )
            if end > start:
                cuts.append(BeatmapCut(start_frame=start, end_frame=end))
    return cuts


def _merge_ranges(cuts: list[BeatmapCut]) -> list[BeatmapCut]:
    merged: list[BeatmapCut] = []
    for cut in sorted(cuts, key=lambda item: (item.start_frame, item.end_frame)):
        if merged and cut.start_frame <= merged[-1].end_frame:
            merged[-1] = BeatmapCut(
                start_frame=merged[-1].start_frame,
                end_frame=max(merged[-1].end_frame, cut.end_frame),
            )
        else:
            merged.append(cut)
    return merged


def _complement(cuts: list[BeatmapCut], duration: int) -> list[BeatmapCut]:
    """Return the kept ranges outside ``cuts`` over ``[0, duration)``."""

    result: list[BeatmapCut] = []
    cursor = 0
    for cut in _merge_ranges(cuts):
        start = max(0, min(duration, cut.start_frame))
        end = max(0, min(duration, cut.end_frame))
        if start > cursor:
            result.append(BeatmapCut(start_frame=cursor, end_frame=start))
        cursor = max(cursor, end)
    if cursor < duration:
        result.append(BeatmapCut(start_frame=cursor, end_frame=duration))
    return result


def _intersect(left: list[BeatmapCut], right: list[BeatmapCut]) -> list[BeatmapCut]:
    result: list[BeatmapCut] = []
    for first in _merge_ranges(left):
        for second in _merge_ranges(right):
            start = max(first.start_frame, second.start_frame)
            end = min(first.end_frame, second.end_frame)
            if end > start:
                result.append(BeatmapCut(start_frame=start, end_frame=end))
    return _merge_ranges(result)


def apply_beatmap(
    state: ProjectState,
    output: Path,
    beatmap: Beatmap | dict[str, Any],
    *,
    expected_revision: int | None = None,
    time_basis: Literal["edited", "timeline", "source"] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> tuple[ProjectState, BeatmapReport, dict[str, Any]]:
    """Apply a beatmap and return ``(new_state, report, sidecar_manifest)``.

    ``keep_ranges`` and ``remove_ranges`` are seconds in ``time_basis``.
    """

    options = beatmap if isinstance(beatmap, Beatmap) else Beatmap.model_validate(beatmap)
    report = BeatmapReport(dry_run=dry_run)
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

    basis = time_basis or options.time_basis
    blocked = _blocked(output)
    updates: dict[str, Any] = {}
    duration = _timeline_duration_frames(state)
    fps = state.media_info.fps_num / state.media_info.fps_den
    before_sec = duration / fps if fps else 0.0

    keep_cuts: list[BeatmapCut] = []
    if options.keep_ranges:
        keep_cuts.extend(_ranges_to_frames(state, options.keep_ranges, basis))
    if options.remove_ranges:
        removed = _ranges_to_frames(state, options.remove_ranges, basis)
        keep_cuts = (
            _intersect(keep_cuts, _complement(removed, duration))
            if keep_cuts
            else _complement(removed, duration)
        )
    keep_cuts = _merge_ranges(keep_cuts)
    cut_requested = bool(options.keep_ranges or options.remove_ranges)

    if cut_requested:
        for cut in keep_cuts:
            if cut.end_frame > duration:
                report.conflicts.append(
                    f"cut {cut.start_frame}-{cut.end_frame} exceeds timeline {duration}"
                )
        if not report.conflicts:
            media = state.media_info
            previous = state.video_segments
            updates["video_segments"] = _cut_video(state.video_segments, keep_cuts)
            updates["audio_segments"] = _cut_audio(
                state.audio_segments,
                keep_cuts,
                (media.fps_num, media.fps_den),
                media.audio_sample_rate,
            )
            report.cuts = len(keep_cuts)
            report.affected_clips = sum(
                1
                for clip in previous
                if any(
                    min(clip.timeline_out_frame, cut.end_frame)
                    > max(clip.timeline_in_frame, cut.start_frame)
                    for cut in keep_cuts
                )
            )
    if not report.conflicts and cut_requested:
        after_frames = max(
            (clip.timeline_out_frame for clip in updates.get("video_segments", [])),
            default=0,
        )
        after_sec = after_frames / fps if fps else 0.0
        report.before_duration_sec = before_sec
        report.after_duration_sec = after_sec
        report.delta_sec = after_sec - before_sec
        report.delta_pct = (report.delta_sec / before_sec * 100.0) if before_sec > 0 else 0.0
        if report.delta_pct < -50.0 and not force and not dry_run:
            report.ok = False
            report.conflicts.append(
                f"planned edit removes {abs(report.delta_pct):.1f}% of the timeline; "
                "pass force=true to confirm"
            )
            raise BeatmapError("destructive edit requires force=true", report=report)

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
                    anchor=entry.anchor,  # type: ignore[arg-type]
                    margin_x=entry.margin_x,
                    margin_y=entry.margin_y,
                    z=entry.z,
                    width_ratio=entry.width_ratio,
                    opacity=entry.opacity,
                    kind="image",
                    layout="fullscreen",
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
        if not dry_run:
            directory = output / "captions"
            directory.mkdir(parents=True, exist_ok=True)
            captions_path = directory / "beatmap.ass"
            captions_path.write_text(
                build_ass_lines(lines, width=1920, height=1080), encoding="utf-8"
            )
            subtitles = output / "subtitles.ass"
            if not subtitles.exists():
                shutil.copy2(captions_path, subtitles)
            sidecar["captions_file"] = str(captions_path)
        report.captions = len(lines)

    updated = refresh_time_map(state.model_copy(update=updates))
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
