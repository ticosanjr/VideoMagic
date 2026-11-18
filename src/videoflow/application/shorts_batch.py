"""Batch Short rendering with per-clip styles and a shared source cache."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.caption_presets import apply_preset
from videoflow.application.captions import build_ass_lines, caption_lines
from videoflow.application.fonts import fonts_dir
from videoflow.application.projects import get_project, load_project_state
from videoflow.application.shorts import short_dimensions, slugify
from videoflow.application.style_catalog import StyleCatalog
from videoflow.domain.config import CaptionStyle
from videoflow.domain.errors import ExportError

LAYOUTS = {"auto", "none", "cutout", "rounded_window", "full_screen"}


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
    fps = media.fps_num / media.fps_den
    discard = set(state.pipeline.discard_sentence_ids)
    kept = [item for item in state.transcript if item.id not in discard]
    renderer = adapter or FFmpegAdapter()
    directory = Path(record.output) / "shorts" / "batch"
    directory.mkdir(parents=True, exist_ok=True)
    rendered: list[dict[str, Any]] = []
    for index, entry in enumerate(clips, start=1):
        if not isinstance(entry, dict):
            continue
        start = max(0.0, float(entry.get("start_sec") or 0.0))
        end = float(entry.get("end_sec") or 0.0)
        if end <= start:
            raise ExportError(f"Shorts batch clip {index} has an invalid range")
        start_sample = round(start * rate)
        end_sample = round(end * rate)
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
        layout = str(entry.get("layout_mode") or (style.layout_mode if style else "auto"))
        if layout not in LAYOUTS:
            layout = "auto"
        target = directory / f"{slugify(title, index)}.mp4"
        intro = entry.get("intro_path")
        music = entry.get("music_path")
        context_source = _source_path(state, record)
        renderer.render_short(
            Path(context_source),
            [(start_sample, end_sample)],
            target,
            sample_rate=rate,
            width=width,
            height=height,
            ass_path=ass_path,
            fontsdir=str(fonts_dir()),
            crop_focus_x=focus,
            crop_focus_y=0.5,
            crop_keyframes=keyframes,
            cutout=layout in {"cutout", "rounded_window"},
            intro_path=Path(intro).expanduser() if intro else None,
            music_path=Path(music).expanduser() if music else None,
        )
        rendered.append(
            {
                "title": title,
                "path": str(target),
                "subtitles": str(ass_path) if ass_path else "",
                "aspect_ratio": aspect,
                "layout": layout,
                "style_id": getattr(style, "style_id", ""),
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "source": str(context_source),
                "fps": round(fps, 6),
            }
        )
    report = directory.parent / "shorts_batch.json"
    report.write_text(
        json.dumps({"ok": True, "clips": rendered}, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "clips": rendered, "manifest": str(report)}


def _source_path(state: Any, record: Any) -> str:
    media = state.media_info
    return str(media.source_path if media is not None else record.primary_source)


__all__ = ["run_shorts_batch"]
