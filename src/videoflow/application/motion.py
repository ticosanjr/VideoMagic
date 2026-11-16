"""Programmatic scene code and an FFmpeg motion renderer.

The scene graph is intentionally JSON-only; the renderer never executes model
code. Each unit becomes a short MP4 that the NLE export places on the overlay
track, so motion graphics work even without a Node/Remotion runtime.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from videoflow.runtime import find_binary

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
)


def find_font() -> str:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    binary = find_binary("fc-match")
    if binary:
        completed = subprocess.run(
            [binary, "-f", "%{file}", "Inter"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        path = completed.stdout.strip()
        if path and Path(path).is_file():
            return path
    return ""


def build_scenes(
    units: Iterable[dict[str, Any]],
    *,
    style: dict[str, Any],
    assets: dict[str, list[dict[str, Any]]],
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    max_scenes: int = 400,
) -> list[dict[str, Any]]:
    palette = [str(item) for item in (style.get("palette") or [])]
    background = palette[0] if palette else "#080B10"
    accent = palette[2] if len(palette) > 2 else "#FF3B30"
    text_color = palette[1] if len(palette) > 1 else "#F8FAFC"
    scenes: list[dict[str, Any]] = []
    for index, unit in enumerate(units):
        if len(scenes) >= max_scenes or not isinstance(unit, dict):
            break
        unit_id = str(unit.get("unit_id") or f"UNIT-{index + 1:04d}")
        duration = max(1.0, float(unit.get("duration_sec") or 5.0))
        assigned = (assets.get(unit_id) or [{}])[0]
        layers: list[dict[str, Any]] = []
        if assigned.get("path"):
            layers.append(
                {
                    "type": assigned.get("kind") or "image",
                    "path": assigned["path"],
                    "fit": "cover",
                    "start_sec": 0.0,
                    "duration_sec": duration,
                }
            )
        layout = str(unit.get("layout") or "presenter_visual")
        if layout in {"lower_third", "full_screen", "presenter_split"}:
            layers.append(
                {
                    "type": "lower_third" if layout == "lower_third" else "panel",
                    "text": str(unit.get("title") or ""),
                    "start_sec": 0.3,
                    "duration_sec": max(1.0, min(duration - 0.6, 6.0)),
                    "color": accent,
                }
            )
        layers.append(
            {
                "type": "title",
                "text": str(unit.get("title") or ""),
                "start_sec": 0.2,
                "duration_sec": max(1.0, min(duration - 0.4, 5.0)),
                "position": "center" if layout == "full_screen" else "upper_left",
                "color": text_color,
            }
        )
        scenes.append(
            {
                "scene_id": f"SCENE-{index + 1:04d}",
                "unit_id": unit_id,
                "title": str(unit.get("title") or ""),
                "narration": str(unit.get("narration") or ""),
                "layout": layout,
                "start_sec": float(unit.get("start_sec") or 0.0),
                "duration_sec": duration,
                "width": width,
                "height": height,
                "fps": fps,
                "background": background,
                "accent": accent,
                "text_color": text_color,
                "layers": layers,
            }
        )
    return scenes


def _dt(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")


def _text_file(directory: Path, scene_id: str, name: str, text: str) -> Path:
    path = directory / f"{scene_id}-{name}.txt"
    path.write_text(text.replace("\n", " ").strip() or " ", encoding="utf-8")
    return path


def render_scene(
    scene: dict[str, Any],
    output_dir: Path,
    *,
    timeout: int = 900,
    draft_scale: float = 1.0,
) -> Path:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise RuntimeError("FFmpeg is not available.")
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_id = str(scene.get("scene_id") or "SCENE")
    target = output_dir / f"{scene_id}.mp4"
    width = max(16, int(int(scene.get("width") or 1920) * draft_scale))
    height = max(16, int(int(scene.get("height") or 1080) * draft_scale))
    duration = max(1.0, float(scene.get("duration_sec") or 5.0))
    fps = int(scene.get("fps") or 30)
    background = str(scene.get("background") or "#080B10").lstrip("#")
    accent = str(scene.get("accent") or "#FF3B30").lstrip("#")
    text_color = str(scene.get("text_color") or "#F8FAFC").lstrip("#")
    layers = [item for item in scene.get("layers") or [] if isinstance(item, dict)]
    asset_layer = next(
        (item for item in layers if item.get("type") in {"image", "video"} and item.get("path")),
        None,
    )
    inputs = [
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x{background}:s={width}x{height}:d={duration:.3f}:r={fps}",
    ]
    filter_parts: list[str] = []
    if asset_layer is not None:
        asset_path = Path(str(asset_layer["path"])).expanduser()
        if asset_path.is_file():
            if asset_layer.get("type") == "image":
                inputs.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", str(asset_path)])
            else:
                inputs.extend(["-t", f"{duration:.3f}", "-i", str(asset_path)])
            filter_parts.append(
                f"[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,trim=duration={duration:.3f},"
                "setpts=PTS-STARTPTS[asset]"
            )
            filter_parts.append("[0:v][asset]overlay=0:0:shortest=1:format=auto[base]")
        else:
            filter_parts.append("[0:v]null[base]")
    else:
        filter_parts.append("[0:v]null[base]")
    current = "base"
    text_dir = output_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    font = find_font()
    for index, layer in enumerate(layers):
        kind = layer.get("type")
        if kind not in {"title", "lower_third", "panel"}:
            continue
        text = str(layer.get("text") or "").strip()
        if not text:
            continue
        path = _text_file(text_dir, scene_id, f"{index}", text)
        start = max(0.0, float(layer.get("start_sec") or 0.0))
        end = min(duration, start + max(0.8, float(layer.get("duration_sec") or 3.0)))
        size = 76 if kind == "title" else 40
        y = "h*0.35" if kind == "title" else "h-260"
        x = "(w-text_w)/2" if kind == "title" else "80"
        drawtext = (
            f"drawtext=textfile='{_dt(str(path))}':fontsize={size}:"
            f"fontcolor=0x{text_color}:x={x}:y={y}:"
            f"alpha='min(1,max(0,(t-{start:.3f})/0.35))':"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
        if font:
            drawtext += f":fontfile='{_dt(font)}'"
        next_name = f"text{index}"
        if kind in {"lower_third", "panel"}:
            filter_parts.append(
                f"[{current}]drawbox=x=60:y=ih-300:w=iw-120:h=180:"
                f"color=0x{accent}@0.82:t=fill:enable='between(t,{start:.3f},{end:.3f})'"
                f"[{next_name}_box]"
            )
            current = f"{next_name}_box"
        filter_parts.append(f"[{current}]{drawtext}[{next_name}]")
        current = next_name
    filter_parts.append(
        f"[{current}]fade=t=in:st=0:d=0.25,fade=t=out:st={max(0.0, duration - 0.25):.3f}:d=0.25[v]"
    )
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
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
        f"{duration:.3f}",
        str(target),
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Motion render failed for {scene_id}: {completed.stderr[-500:]}")
    return target


def write_scenes(output: Path, scenes: list[dict[str, Any]]) -> Path:
    target = Path(output) / "motion" / "scenes.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"scenes": scenes, "count": len(scenes)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def write_render_manifest(output: Path, rendered: list[dict[str, Any]]) -> Path:
    target = Path(output) / "motion" / "render-manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"scenes": rendered, "count": len(rendered)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return target
