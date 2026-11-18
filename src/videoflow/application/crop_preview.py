"""Fast single-frame crop preview for visual framing checks."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from videoflow.application.crop import crop_box
from videoflow.domain.errors import ExportError
from videoflow.runtime import find_binary


def render_crop_preview(
    source: Path,
    output: Path,
    *,
    time_sec: float = 0.0,
    aspect: str = "9:16",
    fx: float = 0.5,
    fy: float = 0.5,
) -> dict[str, Any]:
    from videoflow.adapters.ffmpeg import FFmpegAdapter

    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise ExportError(f"Source does not exist: {source_path}")
    binary = find_binary("ffmpeg")
    if binary is None:
        raise ExportError("FFmpeg is required for crop previews")
    media = FFmpegAdapter().probe(source_path)
    box = crop_box(media.width, media.height, aspect=aspect, fx=fx, fy=fy)
    directory = Path(output).expanduser() / "previews" / "crop"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = int(max(0.0, float(time_sec)) * 1000)
    target = directory / (
        f"crop_{aspect.replace(':', 'x')}_{int(box.focus_x * 100):03d}_"
        f"{int(box.focus_y * 100):03d}_{stamp:09d}.jpg"
    )
    filters = (
        "drawgrid=w=iw/3:h=ih/3:t=1:color=white@0.40,"
        f"drawbox=x={box.x}:y={box.y}:w={box.width}:h={box.height}:"
        "color=red@0.95:t=4"
    )
    completed = subprocess.run(
        [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{max(0.0, float(time_sec)):.6f}",
            "-i",
            str(source_path),
            "-vf",
            filters,
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
            "Crop preview failed: "
            + (completed.stderr.strip()[-400:] or f"exit {completed.returncode}")
        )
    return {
        "ok": True,
        "path": str(target),
        "time_sec": round(max(0.0, float(time_sec)), 3),
        "aspect": aspect,
        "source": {"width": media.width, "height": media.height},
        "crop": box.to_dict(),
    }


__all__ = ["render_crop_preview"]
