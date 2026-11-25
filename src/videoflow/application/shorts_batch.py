"""Batch Short rendering with per-clip styles and a shared source cache."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.adapters.ffmpeg.helpers import (
    ass_font_names,
    prepare_isolated_fonts_dir,
)
from videoflow.application.brand_kit import load_brand_kit
from videoflow.application.caption_presets import apply_preset
from videoflow.application.captions import build_ass_lines, caption_lines
from videoflow.application.crop import crop_box
from videoflow.application.face_track import detect_face_median_x
from videoflow.application.projects import get_project, load_project_state
from videoflow.application.shorts import short_dimensions, slugify
from videoflow.application.shorts_tighten import tighten_clip
from videoflow.application.style_catalog import StyleCatalog
from videoflow.application.thought_boundary import enforce_thought_boundary
from videoflow.domain.config import CaptionStyle
from videoflow.domain.errors import ExportError

LAYOUTS = {
    "auto",
    "none",
    "cutout",
    "rounded_window",
    "full_screen",
    "split_top_visual",
    "headline_card",
    "fullscreen_punchin",
    "pip_bottom_right",
    "split_screen_50_50",
}
MIN_SHORT_DURATION_SEC = 3.0

LAYOUT_ALIASES = {
    "full_face": "fullscreen_punchin",
    "fullscreen": "full_screen",
    "full_reframe": "full_screen",
    "fullscreen_motion": "full_screen",
    "multicam_auto": "auto",
    "presenter_collage": "headline_card",
    "active_speaker_reframe": "full_screen",
    "split_screen": "split_screen_50_50",
    "split_broll": "split_top_visual",
    "split_screen_safe": "split_screen_50_50",
    "cutout": "cutout",
    "rounded_window": "rounded_window",
    "headline_card": "headline_card",
    "depth_3d": "full_screen",
}


class ShortsClipSpec(BaseModel):
    """Strict schema for one ``vf_shorts_batch`` clip.

    Unknown keys are rejected on purpose: a typo such as ``margin_top`` used to
    be ignored silently and produced a render with the wrong layout.
    """

    model_config = ConfigDict(extra="forbid")

    start_sec: float = Field(default=0.0, ge=0.0)
    end_sec: float = Field(default=0.0, ge=0.0)
    time_basis: Literal["edited", "timeline", "source"] = "edited"
    burn_subtitles: bool = True
    source_id: str = ""
    title: str = ""
    style_id: str = ""
    aspect_ratio: str = "9:16"
    fps: int = Field(default=30, ge=15, le=60)
    layout: str = "auto"
    layout_mode: str = ""
    effect: str = ""
    headline_text: str = ""
    intro_path: str = ""
    intro_duration_sec: float = Field(default=2.0, ge=0.0, le=30.0)
    outro_path: str = ""
    outro_duration_sec: float = Field(default=2.0, ge=0.0, le=30.0)
    corner_radius: int = Field(default=0, ge=0)
    crop_keyframes: list[tuple[float, float]] = Field(default_factory=list)
    crop_focus_x: float | None = Field(default=None, ge=0.0, le=1.0)
    face_center_lock: bool = False
    caption_preset: str = ""
    music_path: str = ""
    overlay_path: str = ""
    visual_path: str = ""
    broll_path: str = ""
    second_source_path: str = ""
    punch_in_scale: float = Field(default=1.06, ge=1.0, le=1.10)
    overlay_width_ratio: float = Field(default=0.28, ge=0.05, le=1.0)
    overlay_position: str = "bottom_right"
    overlay_opacity: float = Field(default=0.9, ge=0.0, le=1.0)
    thought_boundary: bool = True
    thought_boundary_max_adjust_sec: float = Field(default=4.0, ge=0.0, le=30.0)
    start_pad_ms: int = Field(default=80, ge=0, le=5000)
    end_pad_ms: int = Field(default=150, ge=0, le=5000)
    max_internal_silence_ms: int = Field(default=500, ge=0, le=10000)
    crossfade_ms: int = Field(default=15, ge=0, le=1000)
    min_sec: float = Field(default=0.0, ge=0.0)
    max_sec: float = Field(default=0.0, ge=0.0)

    @field_validator("layout", "layout_mode")
    @classmethod
    def _normalize_layout(cls, value: str) -> str:
        text = str(value or "").strip().lower()
        return LAYOUT_ALIASES.get(text, text)

    @field_validator("time_basis")
    @classmethod
    def _normalize_time_basis(cls, value: str) -> str:
        text = str(value or "").strip().lower()
        return "edited" if text == "timeline" else text

    def resolved_layout(self, fallback: str = "auto") -> str:
        return self.layout_mode or self.layout or fallback


def _style_for(style_id: str, fallback: str) -> Any:
    catalog = StyleCatalog()
    for identifier in (style_id, fallback):
        if not identifier:
            continue
        try:
            return catalog.get(identifier)
        except Exception:  # noqa: BLE001 - style is optional per clip
            continue
    return None


def run_shorts_batch(
    project_id: str,
    clips: list[dict[str, Any]],
    *,
    adapter: FFmpegAdapter | None = None,
) -> dict[str, Any]:
    record = get_project(project_id)
    state = load_project_state(record)
    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    rate = media.audio_sample_rate
    discard = set(state.pipeline.discard_sentence_ids)
    kept = [item for item in state.transcript if item.id not in discard]
    renderer = adapter or FFmpegAdapter()
    brand = load_brand_kit(record.channel_id or state.style_id)
    directory = Path(record.output) / "shorts" / "batch"
    directory.mkdir(parents=True, exist_ok=True)
    rendered: list[dict[str, Any]] = []
    for index, entry in enumerate(clips, start=1):
        if not isinstance(entry, dict):
            continue
        spec = ShortsClipSpec.model_validate(entry)
        entry = spec.model_dump(mode="python")
        from videoflow.application.time_map import (
            TimeMapError,
            source_range_to_timeline,
            timeline_range_to_source_ranges,
        )

        start = max(0.0, float(spec.start_sec))
        end = float(spec.end_sec)
        if end <= start:
            raise ExportError(f"Shorts batch clip {index} has an invalid range")
        try:
            if spec.time_basis == "source":
                timeline_ranges = source_range_to_timeline(
                    state,
                    start,
                    end,
                    source_id=spec.source_id,
                )
                source_ranges: list[tuple[str, float, float]] = []
                for timeline_start, timeline_end in timeline_ranges:
                    source_ranges.extend(
                        timeline_range_to_source_ranges(
                            state, timeline_start, timeline_end
                        )
                    )
                timeline_start = min(item[0] for item in timeline_ranges)
                timeline_end = max(item[1] for item in timeline_ranges)
            else:
                source_ranges = timeline_range_to_source_ranges(state, start, end)
                timeline_start, timeline_end = start, end
        except TimeMapError as exc:
            raise ExportError(
                f"Shorts batch clip {index} range is outside the edited timeline: {exc}"
            ) from exc
        source_ids = {item[0] for item in source_ranges}
        if len(source_ids) > 1:
            raise ExportError(
                f"Shorts batch clip {index} crosses multiple sources; "
                "render one source per Short"
            )
        words = [word for sentence in kept for word in sentence.words]
        pieces: list[tuple[int, int]] = []
        start_sample = round(source_ranges[0][1] * rate)
        end_sample = round(source_ranges[-1][2] * rate)
        metrics: dict[str, object] = {}
        for _source_id, source_start, source_end in source_ranges:
            range_start = round(source_start * rate)
            range_end = round(source_end * rate)
            if bool(entry.get("thought_boundary", True)):
                boundary = enforce_thought_boundary(
                    kept,
                    range_start,
                    range_end,
                    sample_rate=rate,
                    max_adjust_sec=float(
                        entry.get("thought_boundary_max_adjust_sec") or 4.0
                    ),
                )
                range_start = boundary.start_sample
                range_end = boundary.end_sample
            tightened = tighten_clip(
                start_sample=range_start,
                end_sample=range_end,
                speech_intervals=state.pipeline.speech_intervals,
                words=words,
                sample_rate=rate,
                start_pad_ms=int(entry.get("start_pad_ms") or 110),
                end_pad_ms=int(entry.get("end_pad_ms") or 190),
                max_internal_silence_ms=int(entry.get("max_internal_silence_ms") or 500),
            )
            pieces.extend(tightened.pieces)
            metrics = tightened.metrics
            start_sample = min(start_sample, tightened.start_sample)
            end_sample = max(end_sample, tightened.end_sample)
        if not pieces:
            raise ExportError(f"Shorts batch clip {index} has no active speech")
        # Multiple source ranges can overlap at an edit boundary. Concatenating
        # overlapping spans double-counts samples in the duration gate while
        # FFmpeg renders each sample once, so merge overlaps before rendering.
        merged_pieces: list[tuple[int, int]] = []
        for piece_start, piece_end in pieces:
            if merged_pieces and piece_start < merged_pieces[-1][1]:
                merged_pieces[-1] = (
                    merged_pieces[-1][0],
                    max(merged_pieces[-1][1], piece_end),
                )
            else:
                merged_pieces.append((piece_start, piece_end))
        pieces = merged_pieces
        title = str(entry.get("title") or f"Short {index}")
        style = _style_for(
            str(entry.get("style_id") or ""),
            record.style_id or state.style_id,
        )
        aspect = str(
            entry.get("aspect_ratio") or (style.aspect_ratio if style else "9:16") or "9:16"
        )
        width, height = short_dimensions(aspect)
        layout = str(
            entry.get("layout_mode")
            or entry.get("layout")
            or (style.layout_mode if style else "auto")
        )
        layout = LAYOUT_ALIASES.get(layout, layout)
        if layout not in LAYOUTS:
            raise ExportError(
                f"Unsupported Short layout {layout!r}; expected one of: "
                + ", ".join(sorted(LAYOUTS))
            )
        caption_preset = str(entry.get("caption_preset") or (style.caption_preset if style else ""))
        caption_style = CaptionStyle()
        if caption_preset:
            caption_style = apply_preset(caption_preset, caption_style)
        ass_path: Path | None = None
        if kept:
            lines = caption_lines(
                kept,
                pieces,
                sample_rate=rate,
                word_timing=caption_style.word_timing,
                effect=caption_style.effect,
                max_words=2,
            )
            if lines:
                ass_path = directory / f"{slugify(title, index)}.ass"
                ass_path.write_text(
                    build_ass_lines(
                        lines,
                        style=caption_style,
                        width=width,
                        height=height,
                        layout=layout,
                    ),
                    encoding="utf-8",
                )
        keyframes = [
            (float(item[0]), float(item[1]))
            for item in (entry.get("crop_keyframes") or [])
            if isinstance(item, (list, tuple)) and len(item) >= 2
        ]
        duration = sum(piece_end - piece_start for piece_start, piece_end in pieces) / rate
        context_source = _source_path(state, record, spec.source_id)
        source_media = state.source_media(spec.source_id) if spec.source_id else media
        source_width = max(2, int(getattr(source_media, "width", media.width) or media.width))
        source_height = max(2, int(getattr(source_media, "height", media.height) or media.height))
        face: dict[str, Any] = {}
        source_crop: tuple[int, int, int, int] | None = None
        crop_x: int | None = None
        crop_y: int | None = None
        crop_w: int | None = None
        crop_h: int | None = None
        manual_focus = spec.crop_focus_x is not None
        if manual_focus:
            focus = float(spec.crop_focus_x or 0.0)
            keyframes = [(0.0, focus), (round(duration, 3), focus)]
        elif not keyframes or spec.face_center_lock:
            face = detect_face_median_x(
                context_source,
                start_sample / rate,
                end_sample / rate,
                samples=7,
            )
            box = crop_box(source_width, source_height, aspect=aspect, fx=0.5, fy=0.5)
            crop_w, crop_h = box.width, box.height
            cx = face.get("cx_median")
            if cx is not None:
                crop_x = max(
                    0,
                    min(
                        source_width - crop_w,
                        round(float(cx) * source_width - crop_w / 2),
                    ),
                )
            else:
                crop_x = box.x
            crop_y = box.y
            focus = (
                crop_x / (source_width - crop_w)
                if source_width > crop_w
                else 0.5
            )
            keyframes = [(0.0, focus), (round(duration, 3), focus)]
            source_crop = (crop_w, crop_h, crop_x, crop_y)
        else:
            focus = keyframes[len(keyframes) // 2][1]
        target = directory / f"{slugify(title, index)}.mp4"
        intro = entry.get("intro_path") or brand.get("cta") or ""
        intro_path: Path | None = None
        if intro:
            candidate = Path(str(intro)).expanduser()
            if not candidate.is_file():
                raise ExportError(f"asset_not_found: intro {candidate}")
            if candidate.suffix.casefold() not in {
                ".mp4",
                ".mov",
                ".webm",
                ".m4v",
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            }:
                raise ExportError(f"Unsupported intro asset: {candidate}")
            intro_path = candidate
        outro = entry.get("outro_path") or ""
        outro_path: Path | None = None
        if outro:
            candidate = Path(str(outro)).expanduser()
            if not candidate.is_file():
                raise ExportError(f"asset_not_found: outro {candidate}")
            outro_path = candidate
        music = entry.get("music_path") or brand.get("music") or ""
        overlay = entry.get("overlay_path") or ""
        visual = entry.get("visual_path") or entry.get("broll_path") or ""
        headline = ""
        if layout == "headline_card":
            headline = str(entry.get("headline_text") or entry.get("title") or "")
        clip_seconds = sum(
            round((end - start) / rate * 30) / 30 for start, end in pieces
        )
        expected_duration = clip_seconds
        if intro_path is not None:
            expected_duration += float(entry.get("intro_duration_sec") or 2.0)
        if outro_path is not None:
            expected_duration += float(entry.get("outro_duration_sec") or 2.0)
        if clip_seconds < MIN_SHORT_DURATION_SEC:
            raise ExportError(
                f"Shorts batch clip {index} has invalid_short_duration: "
                f"{clip_seconds:.3f}s is below {MIN_SHORT_DURATION_SEC:.1f}s"
            )
        if spec.min_sec and expected_duration < spec.min_sec:
            raise ExportError(
                f"Shorts batch clip {index} is {expected_duration:.3f}s, "
                f"below min_sec={spec.min_sec:.3f}"
            )
        if spec.max_sec and expected_duration > spec.max_sec:
            raise ExportError(
                f"Shorts batch clip {index} is {expected_duration:.3f}s, "
                f"above max_sec={spec.max_sec:.3f}"
            )
        font_dir = (
            prepare_isolated_fonts_dir(
                record.output,
                ass_font_names(ass_path),
            )
            if spec.burn_subtitles and ass_path is not None
            else None
        )
        renderer.render_short(
            Path(context_source),
            pieces,
            target,
            sample_rate=rate,
            width=width,
            height=height,
            ass_path=ass_path if spec.burn_subtitles else None,
            fontsdir=str(font_dir) if font_dir is not None else None,
            crop_focus_x=focus,
            crop_focus_y=0.5,
            crop_keyframes=keyframes,
            source_crop=source_crop,
            cutout=layout in {"cutout", "rounded_window", "headline_card"},
            layout_mode=layout,
            split_screen=layout == "split_screen_50_50",
            second_source_path=(
                Path(str(entry["second_source_path"]))
                if entry.get("second_source_path")
                else None
            ),
            punch_in_scale=float(entry.get("punch_in_scale") or 1.06),
            visual_path=Path(visual).expanduser() if visual else None,
            headline_text=headline,
            overlay_path=Path(overlay).expanduser() if overlay else None,
            overlay_position=str(entry.get("overlay_position") or "bottom_right"),
            overlay_opacity=float(entry.get("overlay_opacity") or 0.9),
            overlay_width_ratio=float(entry.get("overlay_width_ratio") or 0.28),
            intro_path=intro_path,
            intro_duration_sec=float(entry.get("intro_duration_sec") or 2.0),
            outro_path=outro_path,
            outro_duration_sec=float(entry.get("outro_duration_sec") or 2.0),
            music_path=Path(music).expanduser() if music else None,
            crossfade_ms=int(
                entry.get(
                    "crossfade_ms",
                    tightened.metrics.get("crossfade_ms", 15),
                )
            ),
            fps=30,
        )
        warnings: list[str] = []
        render_impl = getattr(renderer, "render_short", None)
        real_renderer = bool(
            isinstance(renderer, FFmpegAdapter)
            and getattr(render_impl, "__module__", "").startswith("videoflow")
        )
        if target.is_file() and real_renderer:
            from videoflow.application.media_integrity import validate_integrity
            from videoflow.core.media_contract import validate_media

            try:
                expected_frames = round(expected_duration * 30)
                integrity = validate_integrity(
                    target,
                    expected_duration,
                    expected_frames=expected_frames,
                    fps=30.0,
                    tolerance_frames=max(2, len(pieces) + 2),
                )
                if not integrity.ok:
                    raise ExportError(
                        f"Shorts batch clip {index} failed the duration gate: "
                        f"{integrity.reason}"
                    )
                contract = validate_media(target, "deliverable")
                if not contract.ok:
                    first = contract.errors[0] if contract.errors else {}
                    raise ExportError(
                        f"Shorts batch clip {index} violated the media contract: "
                        f"{first.get('code')}: {first.get('message')}"
                    )
                video_sec = integrity.video_sec or 0.0
                audio_sec = integrity.audio_sec or 0.0
                if abs(video_sec - audio_sec) > max(0.12, 3.0 / 30.0):
                    raise ExportError(
                        f"Shorts batch clip {index} video/audio drift "
                        f"{video_sec - audio_sec:+.3f}s"
                    )
            except ExportError as exc:
                # A failed gate must be visible; deleting the file and keeping
                # the clip in the manifest hides a broken deliverable.
                target.unlink(missing_ok=True)
                raise ExportError(
                    f"Shorts batch clip {index} failed validation: {exc}"
                ) from exc
            except Exception as exc:  # noqa: BLE001 - probe is advisory for real files
                warnings.append(f"duration probe failed: {exc}")
        rendered.append(
            {
                "title": title,
                "path": str(target),
                "subtitles": str(ass_path) if ass_path else "",
                "burn_subtitles": spec.burn_subtitles,
                "time_basis": spec.time_basis,
                "aspect_ratio": aspect,
                "layout": layout,
                "style_id": getattr(style, "style_id", ""),
                "source_id": spec.source_id,
                "start_sec": round(timeline_start, 3),
                "end_sec": round(timeline_end, 3),
                "source_start_sec": round(start_sample / rate, 3),
                "source_end_sec": round(end_sample / rate, 3),
                "expected_duration_sec": round(expected_duration, 3),
                "metrics": metrics,
                "pieces": [list(piece) for piece in pieces],
                "timeline_start_sec": round(timeline_start, 3),
                "timeline_end_sec": round(timeline_end, 3),
                "crop_keyframes": [[round(t, 3), round(x, 4)] for t, x in keyframes],
                "crop_x": crop_x,
                "crop_y": crop_y,
                "crop_w": crop_w,
                "crop_h": crop_h,
                "crop_focus_x": round(float(focus), 6),
                "face_cx_median": face.get("cx_median"),
                "face_cy_median": face.get("cy_median"),
                "face_detections": int(face.get("detections") or 0),
                "face_samples": int(face.get("samples") or 0),
                "face_backend": str(face.get("backend") or "manual"),
                "face_fallback_center": bool(
                    face.get("face_fallback_center", False)
                ),
                "source": str(context_source),
                "fps": 30,
                "warnings": warnings,
            }
        )
    report = directory.parent / "shorts_batch.json"
    report.write_text(
        json.dumps({"ok": True, "clips": rendered}, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "clips": rendered, "manifest": str(report)}


def _source_path(state: Any, record: Any, source_id: str = "") -> str:
    media = state.source_media(source_id) if source_id else state.media_info
    return str(media.source_path if media is not None else record.primary_source)


__all__ = ["MIN_SHORT_DURATION_SEC", "run_shorts_batch"]
