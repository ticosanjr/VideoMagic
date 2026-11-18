"""Three-frame caption effect inspector."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from videoflow.application.captions import build_ass_lines, caption_lines
from videoflow.application.fonts import fonts_dir
from videoflow.domain.errors import ExportError
from videoflow.domain.state import ProjectState
from videoflow.runtime import find_binary


def render_caption_preview(
    state: ProjectState,
    output: Path,
    *,
    time_sec: float,
) -> dict[str, Any]:
    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    source = Path(media.source_path).expanduser()
    if not source.is_file():
        raise ExportError(f"Source does not exist: {source}")
    binary = find_binary("ffmpeg")
    if binary is None:
        raise ExportError("FFmpeg is required for caption previews")
    style = state.modules_config.shorts.caption_style
    sample_rate = media.audio_sample_rate
    pieces = [
        (int(clip.source_in_sample), int(clip.source_out_sample))
        for clip in sorted(state.audio_segments, key=lambda item: item.timeline_in_sample)
    ] or [
        (
            0,
            max(
                1,
                round(
                    media.duration_frames
                    * sample_rate
                    / max(0.001, media.fps_num / media.fps_den)
                ),
            ),
        )
    ]
    lines = caption_lines(
        state.transcript,
        pieces,
        sample_rate=sample_rate,
        word_timing=style.word_timing,
        effect=style.effect,
    )
    if not lines:
        raise ExportError("Project has no caption lines to preview")
    active = min(
        lines,
        key=lambda line: abs((line.start + line.end) / 2.0 - max(0.0, float(time_sec))),
    )
    span = max(0.05, min(1.0, active.end - active.start))
    directory = Path(output).expanduser() / "previews" / "captions"
    directory.mkdir(parents=True, exist_ok=True)
    ass_path = directory / f"caption_{int(time_sec * 1000):09d}.ass"
    ass_path.write_text(
        build_ass_lines([active], style=style, width=media.width, height=media.height),
        encoding="utf-8",
    )
    frames: list[dict[str, Any]] = []
    for label, offset in (
        ("before", max(active.start, active.start + span * 0.15)),
        ("word", min(active.end, max(active.start, float(time_sec)))),
        ("after", min(active.end, active.start + span * 0.85)),
    ):
        target = directory / f"caption_{int(time_sec * 1000):09d}_{label}.jpg"
        completed = subprocess.run(
            [
                binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{offset:.6f}",
                "-i",
                str(source),
                "-vf",
                f"ass='{_escape(ass_path)}':fontsdir='{_escape(fonts_dir())}'",
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0 or not target.is_file():
            raise ExportError(
                "Caption preview failed: "
                + (completed.stderr.strip()[-400:] or f"exit {completed.returncode}")
            )
        frames.append(
            {
                "label": label,
                "time_sec": round(offset, 3),
                "path": str(target),
            }
        )
    return {
        "ok": True,
        "caption": {
            "start": active.start,
            "end": active.end,
            "text": active.text,
            "effect": style.effect,
            "words": len(active.words),
            "effect_fallback": active.effect_fallback,
        },
        "ass_path": str(ass_path),
        "frames": frames,
    }


def _escape(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


__all__ = ["render_caption_preview"]
