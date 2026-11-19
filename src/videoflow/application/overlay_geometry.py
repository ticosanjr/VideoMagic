"""Deterministic overlay geometry shared by render, QA, preview, and NLE export."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videoflow.domain.state import OverlayClip, ProjectState
from videoflow.runtime import find_binary


@dataclass(frozen=True, slots=True)
class PixelBox:
    x: int
    y: int
    width: int
    height: int
    z: int = 0

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.width, "h": self.height, "z": self.z}

    def normalised(self, canvas_w: int, canvas_h: int) -> tuple[float, float, float, float]:
        return (
            self.x / max(1, canvas_w),
            self.y / max(1, canvas_h),
            self.right / max(1, canvas_w),
            self.bottom / max(1, canvas_h),
        )


@dataclass(frozen=True, slots=True)
class OverlayLayout:
    overlay_id: str
    path: str
    box: PixelBox
    start_sec: float
    end_sec: float
    anchor: str
    opacity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "overlay_id": self.overlay_id,
            "path": self.path,
            "anchor": self.anchor,
            "opacity": self.opacity,
            "start_sec": round(self.start_sec, 6),
            "end_sec": round(self.end_sec, 6),
            **self.box.to_dict(),
        }


def _even(value: float) -> int:
    return max(2, int(round(value / 2.0)) * 2)


def asset_dimensions(path: Path, kind: str = "image") -> tuple[int, int]:
    """Read real dimensions without relying on the overlay's configured ratio."""

    source = Path(path).expanduser()
    if kind == "image":
        try:
            from PIL import Image

            with Image.open(source) as image:
                return int(image.width), int(image.height)
        except Exception:  # noqa: BLE001 - fall back to ffprobe below
            pass
    binary = find_binary("ffprobe")
    if binary is None:
        return 1, 1
    completed = subprocess.run(
        [
            binary,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    try:
        stream = (json.loads(completed.stdout or "{}").get("streams") or [{}])[0]
        width = int(stream.get("width") or 1)
        height = int(stream.get("height") or 1)
        return max(1, width), max(1, height)
    except (ValueError, TypeError, IndexError):
        return 1, 1


_ALPHA_BBOX_CACHE: dict[tuple[str, int, int], tuple[int, int, int, int] | None] = {}


def asset_alpha_bbox(
    path: Path,
    kind: str = "image",
    *,
    threshold: int = 16,
) -> tuple[int, int, int, int] | None:
    """Return the non-transparent area in source pixels, cached by mtime."""

    source = Path(path).expanduser()
    try:
        stat = source.stat()
    except OSError:
        return None
    key = (str(source.resolve()), stat.st_size, stat.st_mtime_ns)
    if key in _ALPHA_BBOX_CACHE:
        return _ALPHA_BBOX_CACHE[key]
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001 - Pillow is optional
        return None
    image: Any = None
    temporary: Path | None = None
    try:
        if kind == "image":
            image = Image.open(source)
        else:
            binary = find_binary("ffmpeg")
            if binary is None:
                return None
            temporary = source.with_name(f".{source.stem}.alpha-probe.png")
            completed = subprocess.run(
                [
                    binary,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    str(temporary),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if completed.returncode != 0 or not temporary.is_file():
                return None
            image = Image.open(temporary)
        image = image.convert("RGBA")
        alpha = image.getchannel("A").point(lambda value: 255 if value > threshold else 0)
        bbox = alpha.getbbox()
        _ALPHA_BBOX_CACHE[key] = bbox
        return bbox
    except Exception:  # noqa: BLE001 - optional image backend
        _ALPHA_BBOX_CACHE[key] = None
        return None
    finally:
        if image is not None:
            image.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def overlay_box(
    overlay: OverlayClip,
    canvas_w: int,
    canvas_h: int,
    *,
    asset_size: tuple[int, int] | None = None,
) -> PixelBox:
    """Return the exact top-left pixel box for one overlay."""

    width = _even(canvas_w * max(0.001, min(1.0, overlay.width_ratio)))
    image_w, image_h = asset_size or asset_dimensions(Path(overlay.path), overlay.kind)
    height = _even(width * (image_h / max(1, image_w)))
    margin_x = max(0, int(overlay.margin_x))
    margin_y = max(0, int(overlay.margin_y))
    if overlay.anchor == "top_left":
        x, y = margin_x, margin_y
    elif overlay.anchor == "top_center":
        x, y = round((canvas_w - width) / 2) + margin_x, margin_y
    elif overlay.anchor == "top_right":
        x, y = canvas_w - width - margin_x, margin_y
    elif overlay.anchor == "bottom_left":
        x, y = margin_x, canvas_h - height - margin_y
    elif overlay.anchor == "bottom_center":
        x, y = round((canvas_w - width) / 2) + margin_x, canvas_h - height - margin_y
    elif overlay.anchor == "bottom_right":
        x, y = canvas_w - width - margin_x, canvas_h - height - margin_y
    else:
        x, y = round((canvas_w - width) / 2) + margin_x, round(
            (canvas_h - height) / 2
        ) + margin_y
    return PixelBox(x=x, y=y, width=width, height=height, z=overlay.z)


def visual_overlay_box(
    overlay: OverlayClip,
    canvas_w: int,
    canvas_h: int,
    *,
    threshold: int = 16,
) -> PixelBox | None:
    """Bounding box of the non-transparent pixels after scaling to canvas."""

    full = overlay_box(overlay, canvas_w, canvas_h)
    bbox = asset_alpha_bbox(Path(overlay.path), overlay.kind, threshold=threshold)
    if bbox is None:
        return full
    source_w, source_h = asset_dimensions(Path(overlay.path), overlay.kind)
    if source_w <= 0 or source_h <= 0:
        return full
    left, top, right, bottom = bbox
    x = full.x + round(left / source_w * full.width)
    y = full.y + round(top / source_h * full.height)
    width = max(2, round((right - left) / source_w * full.width))
    height = max(2, round((bottom - top) / source_h * full.height))
    width = min(width, max(2, canvas_w - x))
    height = min(height, max(2, canvas_h - y))
    return PixelBox(x=x, y=y, width=width, height=height, z=full.z)


def caption_box(
    style: Any,
    canvas_w: int,
    canvas_h: int,
    *,
    text: str = "",
    max_lines: int = 2,
) -> PixelBox:
    """Estimate the ASS caption band from its real style and margins."""

    width = _even(canvas_w * max(0.1, min(1.0, float(style.max_width))))
    font = max(8, int(getattr(style, "font_size", 72)))
    height = _even(font * 1.30 * max(1, min(4, max_lines)))
    x = round((canvas_w - width) / 2)
    center_y = float(getattr(style, "position_y", 0.78)) * canvas_h
    y = round(center_y - height / 2)
    y = max(0, min(canvas_h - height, y))
    return PixelBox(x=x, y=y, width=width, height=height, z=40)


def overlap(left: PixelBox, right: PixelBox) -> bool:
    return not (
        left.right <= right.x
        or right.right <= left.x
        or left.bottom <= right.y
        or right.bottom <= left.y
    )


def overlap_pixels(left: PixelBox, right: PixelBox) -> int:
    width = max(0, min(left.right, right.right) - max(left.x, right.x))
    height = max(0, min(left.bottom, right.bottom) - max(left.y, right.y))
    return width * height


def layout_for(
    state: ProjectState,
    canvas_w: int,
    canvas_h: int,
) -> list[OverlayLayout]:
    media = state.media_info
    fps = (media.fps_num / media.fps_den) if media is not None and media.fps_den else 30.0
    result: list[OverlayLayout] = []
    for overlay in sorted(state.overlays, key=lambda item: (item.z, item.start_frame)):
        box = overlay_box(overlay, canvas_w, canvas_h)
        result.append(
            OverlayLayout(
                overlay_id=overlay.overlay_id,
                path=overlay.path,
                box=box,
                start_sec=overlay.start_frame / fps,
                end_sec=(overlay.start_frame + overlay.duration_frames) / fps,
                anchor=overlay.anchor,
                opacity=overlay.opacity,
            )
        )
    return result


def _temporal_overlap(
    left: OverlayLayout, right: OverlayLayout
) -> tuple[float, float] | None:
    start = max(left.start_sec, right.start_sec)
    end = min(left.end_sec, right.end_sec)
    return (start, end) if end > start else None


def collisions(
    state: ProjectState,
    canvas_w: int,
    canvas_h: int,
    *,
    caption: PixelBox | None = None,
    mode: str = "visual",
) -> list[dict[str, Any]]:
    """Return real spatial collisions between overlays and/or captions.

    ``visual`` uses only the non-transparent pixels; ``rectangle`` keeps the
    legacy full bounding box and is available by explicit request.
    """

    layouts = layout_for(state, canvas_w, canvas_h)
    boxes: dict[str, PixelBox | None] = {}
    if mode in {"visual", "bbox"}:
        for overlay in state.overlays:
            boxes[overlay.overlay_id] = visual_overlay_box(
                overlay, canvas_w, canvas_h
            )
    else:
        boxes = {layout.overlay_id: layout.box for layout in layouts}
    issues: list[dict[str, Any]] = []
    for index, left in enumerate(layouts):
        left_box = boxes.get(left.overlay_id)
        if left_box is None:
            continue
        for right in layouts[index + 1 :]:
            right_box = boxes.get(right.overlay_id)
            if right_box is None:
                continue
            window = _temporal_overlap(left, right)
            if window is None or not overlap(left_box, right_box):
                continue
            issues.append(
                {
                    "kind": "overlay_overlap",
                    "item_a": left.overlay_id,
                    "item_b": right.overlay_id,
                    "overlap_px": overlap_pixels(left_box, right_box),
                    "start_sec": round(window[0], 3),
                    "end_sec": round(window[1], 3),
                }
            )
        if caption is not None and overlap(left_box, caption):
            issues.append(
                {
                    "kind": "caption_overlap",
                    "item_a": left.overlay_id,
                    "item_b": "captions",
                    "overlap_px": overlap_pixels(left_box, caption),
                    "start_sec": round(left.start_sec, 3),
                    "end_sec": round(left.end_sec, 3),
                }
            )
    return issues


def layout_payload(
    state: ProjectState,
    canvas_w: int,
    canvas_h: int,
    *,
    caption: PixelBox | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "canvas": {"width": canvas_w, "height": canvas_h},
        "overlays": [item.to_dict() for item in layout_for(state, canvas_w, canvas_h)],
        "caption": caption.to_dict() if caption is not None else None,
        "collisions": collisions(state, canvas_w, canvas_h, caption=caption),
    }


def write_layout(
    state: ProjectState,
    output: Path,
    canvas_w: int,
    canvas_h: int,
    *,
    caption: PixelBox | None = None,
) -> Path:
    target = Path(output).expanduser() / "layout.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(layout_payload(state, canvas_w, canvas_h, caption=caption), indent=2)
        + "\n",
        encoding="utf-8",
    )
    return target


def auto_pack(
    state: ProjectState,
    canvas_w: int,
    canvas_h: int,
    *,
    caption: PixelBox | None = None,
    gap: int = 16,
) -> list[dict[str, Any]]:
    """Resolve vertical collisions by moving lower layers away from captions."""

    layouts = layout_for(state, canvas_w, canvas_h)
    changes: list[dict[str, Any]] = []
    if caption is None:
        return changes
    for item in layouts:
        if item.box.z >= caption.z or not overlap(item.box, caption):
            continue
        direction = -1 if item.box.y < caption.y else 1
        delta = gap + (
            caption.y - item.box.bottom if direction < 0 else item.box.y - caption.bottom
        )
        delta = max(gap, delta)
        overlay = next(
            (candidate for candidate in state.overlays if candidate.overlay_id == item.overlay_id),
            None,
        )
        if overlay is None:
            continue
        changes.append(
            {
                "overlay_id": overlay.overlay_id,
                "margin_y": max(0, overlay.margin_y + delta) if direction < 0 else overlay.margin_y,
                "delta_y": -delta if direction < 0 else delta,
            }
        )
    return changes


__all__ = [
    "OverlayLayout",
    "PixelBox",
    "asset_dimensions",
    "auto_pack",
    "caption_box",
    "collisions",
    "layout_for",
    "layout_payload",
    "overlap",
    "overlap_pixels",
    "overlay_box",
    "write_layout",
]
