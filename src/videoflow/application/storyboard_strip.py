"""One-image storyboard strip for fast visual review in OpenCode."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from videoflow.domain.errors import ExportError
from videoflow.runtime import find_binary


def _probe_size(source: Path) -> tuple[int, int]:
    from videoflow.adapters.ffmpeg import FFmpegAdapter

    media = FFmpegAdapter().probe(source)
    return max(1, media.width), max(1, media.height)


def _extract_frame(source: Path, target: Path, time_sec: float, width: int) -> bool:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise ExportError("FFmpeg is required for storyboard strips")
    completed = subprocess.run(
        [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{max(0.0, time_sec):.6f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return completed.returncode == 0 and target.is_file()


def build_storyboard_strip(
    source: str | Path,
    output: str | Path,
    *,
    start_sec: float = 0.0,
    end_sec: float = 0.0,
    cols: int = 5,
    annotate: bool = True,
    cell_width: int = 320,
) -> dict[str, Any]:
    """Render a contact sheet of evenly sampled frames in one PNG."""

    path = Path(source).expanduser()
    if not path.is_file():
        raise ExportError(f"Storyboard source does not exist: {path}")
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:  # noqa: BLE001 - optional dependency
        raise ExportError("Pillow is required for storyboard strips") from exc
    duration = max(0.0, float(end_sec) - float(start_sec))
    if duration <= 0:
        from videoflow.adapters.ffmpeg import FFmpegAdapter

        media = FFmpegAdapter().probe(path)
        duration = media.duration_frames / max(
            1e-6, media.fps_num / media.fps_den
        )
        end_sec = float(start_sec) + duration
    columns = max(1, min(int(cols), 8))
    rows = 2
    count = columns * rows
    source_width, source_height = _probe_size(path)
    width = max(96, min(int(cell_width), 480))
    height = max(54, round(width * source_height / max(1, source_width)))
    times = [
        float(start_sec) + (duration * index / max(1, count - 1))
        for index in range(count)
    ]
    target_dir = Path(output).expanduser() / "storyboards"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (
        f"storyboard_{int(float(start_sec) * 1000):09d}_"
        f"{int(float(end_sec) * 1000):09d}.png"
    )
    with tempfile.TemporaryDirectory(prefix="vf-storyboard-") as raw:
        directory = Path(raw)
        frames: list[tuple[float, Path]] = []
        for index, time_sec in enumerate(times):
            frame = directory / f"frame-{index:03d}.jpg"
            if _extract_frame(path, frame, time_sec, width):
                frames.append((time_sec, frame))
        if not frames:
            raise ExportError("Storyboard could not extract any frame")
        canvas = Image.new("RGB", (columns * width, rows * height), (18, 18, 22))
        draw = ImageDraw.Draw(canvas)
        for index, (time_sec, frame_path) in enumerate(frames[:count]):
            with Image.open(frame_path) as image:
                image = image.convert("RGB")
                image = image.resize((width, height))
                x = (index % columns) * width
                y = (index // columns) * height
                canvas.paste(image, (x, y))
            if annotate:
                label = f"{time_sec:.1f}s"
                draw.rectangle((x + 4, y + 4, x + 74, y + 22), fill=(0, 0, 0))
                draw.text((x + 8, y + 6), label, fill=(255, 255, 255))
                margin_x = max(4, round(width * 0.05))
                margin_y = max(4, round(height * 0.05))
                draw.rectangle(
                    (x + margin_x, y + margin_y, x + width - margin_x, y + height - margin_y),
                    outline=(255, 210, 80),
                    width=1,
                )
            draw.rectangle((x, y, x + width, y + height), outline=(60, 60, 70))
        canvas.save(target, format="PNG")
    return {
        "ok": True,
        "path": str(target),
        "frames": len(frames[:count]),
        "times": [round(item, 3) for item in times[: len(frames)]],
        "width": int(canvas.width),
        "height": int(canvas.height),
    }


__all__ = ["build_storyboard_strip"]
