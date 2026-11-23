"""High-retention intro compiler built from approved assets."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg.helpers import escape_ffmpeg_filter_path
from videoflow.application.motion import find_font
from videoflow.runtime import find_binary


def _asset_paths(assets: Iterable[dict[str, Any]], limit: int) -> list[Path]:
    paths: list[Path] = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("downloaded_path") or "")
        if not raw:
            continue
        path = Path(raw)
        if path.is_file():
            paths.append(path)
        if len(paths) >= limit:
            break
    return paths


def compile_intro(
    output: Path,
    *,
    assets: Iterable[dict[str, Any]],
    duration_sec: float = 112.0,
    clip_seconds: float = 2.0,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    title: str = "VideoFlow",
    max_assets: int = 60,
) -> dict[str, Any]:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise RuntimeError("FFmpeg is not available.")
    directory = Path(output) / "motion"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "intro.mp4"
    paths = _asset_paths(assets, max_assets)
    if not paths:
        target = _title_card(
            binary, directory, title=title, duration_sec=min(8.0, duration_sec),
            width=width, height=height, fps=fps
        )
        return {
            "available": True,
            "mode": "title_card",
            "path": str(target),
            "duration_sec": min(8.0, duration_sec),
            "asset_count": 0,
        }
    clip = max(0.5, min(6.0, clip_seconds))
    count = max(1, min(len(paths), int(duration_sec / clip), max_assets))
    paths = paths[:count]
    inputs: list[str] = []
    filters: list[str] = []
    for index, path in enumerate(paths):
        if path.suffix.casefold() in {".jpg", ".jpeg", ".png", ".webp"}:
            inputs.extend(["-loop", "1", "-t", f"{clip:.3f}", "-i", str(path)])
        else:
            inputs.extend(["-t", f"{clip:.3f}", "-i", str(path)])
        filters.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},trim=duration={clip:.3f},"
            f"setpts=PTS-STARTPTS[v{index}]"
        )
    filters.append(
        "".join(f"[v{index}]" for index in range(len(paths)))
        + f"concat=n={len(paths)}:v=1:a=0[cut]"
    )
    text_file = directory / "intro-title.txt"
    text_file.write_text(title.replace("\n", " "), encoding="utf-8")
    font = find_font()
    drawtext = (
        f"drawtext=textfile='{text_file}':fontsize=110:fontcolor=white:"
        "x=(w-text_w)/2:y=h*0.42:alpha='min(1,max(0,(t-0.2)/0.5))':"
        "enable='between(t,0.2,3.2)'"
    )
    if font:
        drawtext += f":fontfile='{escape_ffmpeg_filter_path(font)}'"
    filters.append(f"[cut]{drawtext}[v]")
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-t",
        f"{count * clip:.3f}",
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Intro render failed: {completed.stderr[-500:]}")
    return {
        "available": True,
        "mode": "asset_montage",
        "path": str(target),
        "duration_sec": count * clip,
        "asset_count": count,
    }


def _title_card(
    binary: str,
    directory: Path,
    *,
    title: str,
    duration_sec: float,
    width: int,
    height: int,
    fps: int,
) -> Path:
    target = directory / "intro.mp4"
    text_file = directory / "intro-title.txt"
    text_file.write_text(title.replace("\n", " "), encoding="utf-8")
    font = find_font()
    drawtext = (
        f"drawtext=textfile='{text_file}':fontsize=110:fontcolor=white:"
        "x=(w-text_w)/2:y=h*0.42"
    )
    if font:
        drawtext += f":fontfile='{escape_ffmpeg_filter_path(font)}'"
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x080B10:s={width}x{height}:d={duration_sec:.3f}:r={fps}",
        "-vf",
        drawtext,
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-t",
        f"{duration_sec:.3f}",
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Intro title card failed: {completed.stderr[-500:]}")
    return target


def write_manifest(output: Path, payload: dict[str, Any]) -> Path:
    path = Path(output) / "motion" / "intro.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
