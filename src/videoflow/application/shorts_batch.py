"""Batch Short rendering with per-clip styles and a shared source cache."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.brand_kit import load_brand_kit
from videoflow.application.caption_presets import apply_preset
from videoflow.application.captions import build_ass_lines, caption_lines
from videoflow.application.fonts import fonts_dir
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
LAYOUT_ALIASES = {
    "fullscreen": "full_screen",
    "full_reframe": "full_screen",
    "fullscreen_motion": "full_screen",
    "multicam_auto": "auto",
    "presenter_collage": "headline_card",
    "active_speaker_reframe": "full_screen",
    "split_screen": "split_screen_50_50",
}


class ShortsClipSpec(BaseModel):
    """Strict schema for one ``vf_shorts_batch`` clip.

    Unknown keys are rejected on purpose: a typo such as ``margin_top`` used to
    be ignored silently and produced a render with the wrong layout.
    """

    model_config = ConfigDict(extra="forbid")

    start_sec: float = Field(default=0.0, ge=0.0)
    end_sec: float = Field(default=0.0, ge=0.0)
    time_basis: Literal["timeline", "source"] = "timeline"
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
        text = str(value or "").strip()
        return LAYOUT_ALIASES.get(text, text)

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
        start = max(0.0, float(spec.start_sec))
        end = float(spec.end_sec)
        if spec.time_basis == "source":
            from videoflow.application.time_map import TimeMapError, source_to_timeline_sec

            try:
                start = source_to_timeline_sec(state, start, source_id=spec.source_id)
                end = source_to_timeline_sec(state, end, source_id=spec.source_id)
            except TimeMapError as exc:
                raise ExportError(
                    f"Shorts batch clip {index} source range is invalid: {exc}"
                ) from exc
        if end <= start:
            raise ExportError(f"Shorts batch clip {index} has an invalid range")
        start_sample = round(start * rate)
        end_sample = round(end * rate)
        if bool(entry.get("thought_boundary", True)):
            boundary = enforce_thought_boundary(
                kept,
                start_sample,
                end_sample,
                sample_rate=rate,
                max_adjust_sec=float(entry.get("thought_boundary_max_adjust_sec") or 4.0),
            )
            start_sample = boundary.start_sample
            end_sample = boundary.end_sample
        words = [
            word
            for sentence in kept
            for word in sentence.words
        ]
        tightened = tighten_clip(
            start_sample=start_sample,
            end_sample=end_sample,
            speech_intervals=state.pipeline.speech_intervals,
            words=words,
            sample_rate=rate,
            start_pad_ms=int(entry.get("start_pad_ms") or 80),
            end_pad_ms=int(entry.get("end_pad_ms") or 150),
            max_internal_silence_ms=int(entry.get("max_internal_silence_ms") or 500),
        )
        start_sample = tightened.start_sample
        end_sample = tightened.end_sample
        title = str(entry.get("title") or f"Short {index}")
        style = _style_for(
            str(entry.get("style_id") or ""),
            record.style_id or state.style_id,
        )
        aspect = str(
            entry.get("aspect_ratio") or (style.aspect_ratio if style else "9:16") or "9:16"
        )
        width, height = short_dimensions(aspect)
        caption_preset = str(entry.get("caption_preset") or (style.caption_preset if style else ""))
        caption_style = CaptionStyle()
        if caption_preset:
            caption_style = apply_preset(caption_preset, caption_style)
        ass_path: Path | None = None
        if kept:
            lines = caption_lines(
                kept,
                [(start_sample, end_sample)],
                sample_rate=rate,
                word_timing=caption_style.word_timing,
                effect=caption_style.effect,
            )
            if lines:
                ass_path = directory / f"{slugify(title, index)}.ass"
                ass_path.write_text(
                    build_ass_lines(lines, style=caption_style, width=width, height=height),
                    encoding="utf-8",
                )
        keyframes = [
            (float(item[0]), float(item[1]))
            for item in (entry.get("crop_keyframes") or [])
            if isinstance(item, (list, tuple)) and len(item) >= 2
        ]
        focus = keyframes[len(keyframes) // 2][1] if keyframes else 0.5
        if not keyframes:
            duration = (
                sum(piece_end - piece_start for piece_start, piece_end in tightened.pieces)
                / rate
            )
            keyframes = [(0.0, focus), (round(duration, 3), focus)]
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
        context_source = _source_path(state, record, spec.source_id)
        renderer.render_short(
            Path(context_source),
            list(tightened.pieces),
            target,
            sample_rate=rate,
            width=width,
            height=height,
            ass_path=ass_path,
            fontsdir=str(fonts_dir()),
            crop_focus_x=focus,
            crop_focus_y=0.5,
            crop_keyframes=keyframes,
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
            crossfade_ms=int(tightened.metrics.get("crossfade_ms") or 15),
            fps=int(spec.fps),
        )
        clip_seconds = sum(end - start for start, end in tightened.pieces) / rate
        expected_duration = clip_seconds
        if intro_path is not None:
            expected_duration += float(entry.get("intro_duration_sec") or 2.0)
        if outro_path is not None:
            expected_duration += float(entry.get("outro_duration_sec") or 2.0)
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
        warnings: list[str] = []
        probe = getattr(renderer, "probe", None)
        if callable(probe):
            try:
                probed = probe(target)
                expected_frames = round(expected_duration * spec.fps)
                if abs(int(probed.duration_frames) - expected_frames) > 1:
                    raise ExportError(
                        f"Shorts batch clip {index} rendered "
                        f"{probed.duration_frames} frames, expected {expected_frames}"
                    )
            except ExportError:
                raise
            except Exception as exc:  # noqa: BLE001 - probe is advisory for fakes
                warnings.append(f"duration probe failed: {exc}")
        rendered.append(
            {
                "title": title,
                "path": str(target),
                "subtitles": str(ass_path) if ass_path else "",
                "aspect_ratio": aspect,
                "layout": layout,
                "style_id": getattr(style, "style_id", ""),
                "source_id": spec.source_id,
                "start_sec": round(start_sample / rate, 3),
                "end_sec": round(end_sample / rate, 3),
                "expected_duration_sec": round(expected_duration, 3),
                "metrics": tightened.metrics,
                "pieces": [list(piece) for piece in tightened.pieces],
                "crop_keyframes": [[round(t, 3), round(x, 4)] for t, x in keyframes],
                "source": str(context_source),
                "fps": int(spec.fps),
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


__all__ = ["run_shorts_batch"]
