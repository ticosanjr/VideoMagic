"""Normalized crop geometry shared by Short rendering and QA previews."""

from __future__ import annotations

from dataclasses import dataclass

ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "16:9": (16, 9),
    "9:16": (9, 16),
    "4:5": (4, 5),
    "3:4": (3, 4),
    "2:3": (2, 3),
    "1:1": (1, 1),
}


@dataclass(frozen=True, slots=True)
class CropBox:
    width: int
    height: int
    x: int
    y: int
    focus_x: float
    focus_y: float

    def to_dict(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "x": self.x,
            "y": self.y,
            "focus_x": self.focus_x,
            "focus_y": self.focus_y,
        }


def parse_aspect(value: str) -> tuple[int, int]:
    raw = str(value or "").strip().lower().replace(" ", "")
    if raw in ASPECT_RATIOS:
        return ASPECT_RATIOS[raw]
    if ":" in raw:
        left, right = raw.split(":", 1)
        try:
            width, height = int(left), int(right)
        except ValueError as exc:
            raise ValueError(f"invalid aspect ratio: {value}") from exc
        if width > 0 and height > 0:
            return width, height
    raise ValueError(f"invalid aspect ratio: {value}")


def crop_box(
    source_width: int,
    source_height: int,
    *,
    aspect: str = "9:16",
    fx: float = 0.5,
    fy: float = 0.5,
) -> CropBox:
    """Return an even-dimension crop box normalized to the source frame."""

    if source_width <= 0 or source_height <= 0:
        raise ValueError("source dimensions must be positive")
    ratio_num, ratio_den = parse_aspect(aspect)
    target = ratio_num / ratio_den
    source = source_width / source_height
    if target < source:
        width = source_height * ratio_num / ratio_den
        height = float(source_height)
    else:
        width = float(source_width)
        height = source_width / target
    width = max(2, int(round(width / 2)) * 2)
    height = max(2, int(round(height / 2)) * 2)
    width = min(width, source_width - (source_width % 2))
    height = min(height, source_height - (source_height % 2))
    focus_x = max(0.0, min(1.0, float(fx)))
    focus_y = max(0.0, min(1.0, float(fy)))
    x = max(0, min(source_width - width, int(round((source_width - width) * focus_x))))
    y = max(0, min(source_height - height, int(round((source_height - height) * focus_y))))
    return CropBox(width, height, x, y, focus_x, focus_y)


def face_center_focus(
    face_center_x: float,
    *,
    source_width: int,
    crop_width: int,
) -> float:
    """Convert a normalized face center to the crop x focus.

    ``face_center_x`` is the horizontal center of the detected face in the
    source frame (0..1). The returned value is the normalized crop offset that
    puts that center exactly on the middle of the output frame.
    """

    source_width = max(1, int(source_width))
    crop_width = max(2, min(int(crop_width), source_width))
    if source_width <= crop_width:
        return 0.5
    center = max(0.0, min(1.0, float(face_center_x))) * source_width
    crop_x = max(0.0, min(float(source_width - crop_width), center - crop_width / 2))
    return round(crop_x / (source_width - crop_width), 6)


def crop_filter(
    width: int,
    height: int,
    *,
    fx: float = 0.5,
    fy: float = 0.5,
) -> str:
    """FFmpeg crop expression with normalized focus and rounded pixels."""

    focus_x = max(0.0, min(1.0, float(fx)))
    focus_y = max(0.0, min(1.0, float(fy)))
    return (
        f"crop={width}:{height}:"
        f"round((iw-ow)*{focus_x:.6f}):"
        f"round((ih-oh)*{focus_y:.6f})"
    )


__all__ = [
    "ASPECT_RATIOS",
    "CropBox",
    "crop_box",
    "crop_filter",
    "face_center_focus",
    "parse_aspect",
]
