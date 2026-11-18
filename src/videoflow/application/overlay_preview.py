"""Fast single-frame overlay and safe-zone inspector."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from videoflow.application.overlay_geometry import (
    caption_box,
    collisions,
    layout_for,
    layout_payload,
    write_layout,
)
from videoflow.domain.errors import ExportError
from videoflow.domain.state import ProjectState
from videoflow.runtime import find_binary


def render_overlay_preview(
    state: ProjectState,
    output: Path,
    *,
    time_sec: float = 0.0,
    platform: str = "youtube_16_9",
) -> dict[str, Any]:
    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    source = Path(media.source_path).expanduser()
    if not source.is_file():
        raise ExportError(f"Source does not exist: {source}")
    binary = find_binary("ffmpeg")
    if binary is None:
        raise ExportError("FFmpeg is required for overlay previews")
    directory = Path(output).expanduser() / "previews" / "overlay"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = int(max(0.0, float(time_sec)) * 1000)
    frame_path = directory / f"frame_{stamp:09d}.jpg"
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
            str(source),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(frame_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0 or not frame_path.is_file():
        raise ExportError(
            "Overlay preview frame failed: "
            + (completed.stderr.strip()[-400:] or f"exit {completed.returncode}")
        )
    style = state.modules_config.shorts.caption_style
    caption = caption_box(style, media.width, media.height)
    target = directory / f"overlay_{platform}_{stamp:09d}.jpg"
    _draw(frame_path, target, state, caption)
    layout_path = write_layout(state, Path(output), media.width, media.height, caption=caption)
    return {
        "ok": True,
        "path": str(target),
        "layout_path": str(layout_path),
        "time_sec": round(max(0.0, float(time_sec)), 3),
        "platform": platform,
        "overlays": [item.to_dict() for item in layout_for(state, media.width, media.height)],
        "caption": caption.to_dict(),
        "collisions": collisions(state, media.width, media.height, caption=caption),
        "layout": layout_payload(state, media.width, media.height, caption=caption),
    }


def _draw(
    frame_path: Path,
    target: Path,
    state: ProjectState,
    caption: Any,
) -> None:
    from PIL import Image, ImageDraw

    with Image.open(frame_path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    for item in layout_for(state, width, height):
        box = item.box
        color = (255, 64, 64, 230)
        draw.rectangle(
            [box.x, box.y, box.x + box.width, box.y + box.height],
            outline=color,
            width=max(2, width // 360),
        )
        label = f"{item.overlay_id} z={box.z} ({box.x},{box.y},{box.width},{box.height})"
        draw.text((max(0, box.x + 6), max(0, box.y + 6)), label, fill=color)
    draw.rectangle(
        [caption.x, caption.y, caption.x + caption.width, caption.y + caption.height],
        outline=(64, 220, 255, 230),
        width=max(2, width // 360),
    )
    draw.text(
        (max(0, caption.x + 6), max(0, caption.y + 6)),
        f"caption z=40 ({caption.x},{caption.y},{caption.width},{caption.height})",
        fill=(64, 220, 255, 255),
    )
    try:
        from videoflow.steps.qa_safezone import SAFE_ZONES

        for zone in SAFE_ZONES.get("youtube_16_9", ()):
            draw.rectangle(
                [
                    round(zone.x * width),
                    round(zone.y * height),
                    round((zone.x + zone.width) * width),
                    round((zone.y + zone.height) * height),
                ],
                outline=(255, 200, 0, 220),
                width=max(1, width // 480),
            )
    except Exception:  # noqa: BLE001 - safe-zone overlay is advisory
        pass
    image.save(target, quality=92)


__all__ = ["render_overlay_preview"]
