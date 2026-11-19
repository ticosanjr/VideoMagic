"""Canvas geometry, Shorts layouts, safe zones, and crop math."""

from __future__ import annotations

from dataclasses import dataclass

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
DEFAULT_HEADROOM = 0.38
MAX_FACE_UPSCALE = 2.5

SHORTS_BOTTOM_SAFE = "shorts_bottom"
SHORTS_RIGHT_SAFE = "shorts_right"


@dataclass(frozen=True, slots=True)
class CanvasRegion:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0

    @property
    def aspect(self) -> float:
        return self.width / max(1, self.height)

    def contains(self, other: CanvasRegion) -> bool:
        return (
            other.x >= self.x
            and other.y >= self.y
            and other.right <= self.right
            and other.bottom <= self.bottom
        )

    def overlaps(self, other: CanvasRegion) -> bool:
        return not (
            other.x >= self.right
            or other.right <= self.x
            or other.y >= self.bottom
            or other.bottom <= self.y
        )


@dataclass(frozen=True, slots=True)
class LayoutGeometry:
    layout: str
    face: CanvasRegion
    screen: CanvasRegion | None
    broll: CanvasRegion | None
    subtitle_y: int

    @property
    def face_aspect(self) -> float:
        return self.face.aspect


LAYOUTS: dict[str, LayoutGeometry] = {
    "FULL_FACE": LayoutGeometry(
        layout="FULL_FACE",
        face=CanvasRegion(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT),
        screen=None,
        broll=None,
        subtitle_y=1360,
    ),
    "SPLIT_BROLL": LayoutGeometry(
        layout="SPLIT_BROLL",
        face=CanvasRegion(0, 0, CANVAS_WIDTH, 960),
        screen=None,
        broll=CanvasRegion(0, 960, CANVAS_WIDTH, 960),
        subtitle_y=960,
    ),
    "SPLIT_SCREEN_SAFE": LayoutGeometry(
        layout="SPLIT_SCREEN_SAFE",
        face=CanvasRegion(0, 840, CANVAS_WIDTH, 700),
        screen=CanvasRegion(0, 0, CANVAS_WIDTH, 840),
        broll=None,
        subtitle_y=840,
    ),
    "SPLIT_SCREEN_FILL": LayoutGeometry(
        layout="SPLIT_SCREEN_FILL",
        face=CanvasRegion(0, 768, CANVAS_WIDTH, 1152),
        screen=CanvasRegion(0, 0, CANVAS_WIDTH, 768),
        broll=None,
        subtitle_y=768,
    ),
}

# YouTube Shorts UI keeps the bottom 380 px and the right 140 px clear.
SAFE_ZONES: dict[str, CanvasRegion] = {
    SHORTS_BOTTOM_SAFE: CanvasRegion(0, 1540, CANVAS_WIDTH, 380),
    SHORTS_RIGHT_SAFE: CanvasRegion(940, 0, 140, CANVAS_HEIGHT),
}
CONTENT_REGION = CanvasRegion(0, 0, 940, 1540)


@dataclass(frozen=True, slots=True)
class CropBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True, slots=True)
class FaceBox:
    cx: float
    cy: float
    w: float
    h: float


def layout_geometry(layout: str) -> LayoutGeometry:
    try:
        return LAYOUTS[layout]
    except KeyError as exc:
        raise ValueError(f"unknown Short layout: {layout}") from exc


def subtitle_y_map() -> dict[str, int]:
    return {name: item.subtitle_y for name, item in LAYOUTS.items()}


def caption_region(
    layout: str,
    *,
    lines: int = 2,
    font_px: int = 64,
    line_height: float = 1.18,
    max_width: int = 800,
) -> CanvasRegion:
    geometry = layout_geometry(layout)
    height = round(max(1, lines) * font_px * line_height)
    return CanvasRegion(
        x=(CANVAS_WIDTH - max_width) // 2,
        y=geometry.subtitle_y - height // 2,
        width=max_width,
        height=height,
    )


def captions_are_safe(layout: str, **kwargs: int | float) -> bool:
    region = caption_region(layout, **kwargs)  # type: ignore[arg-type]
    return not any(region.overlaps(zone) for zone in SAFE_ZONES.values())


def clamp_crop(
    *,
    focus_x: float,
    focus_y: float,
    crop_w: float,
    crop_h: float,
    cam_w: int,
    cam_h: int,
    headroom: float = DEFAULT_HEADROOM,
) -> CropBox:
    width = max(2, min(int(round(crop_w)), cam_w))
    height = max(2, min(int(round(crop_h)), cam_h))
    x = int(round(focus_x * cam_w - width / 2.0))
    y = int(round(focus_y * cam_h - height * max(0.0, min(1.0, headroom))))
    x = max(0, min(cam_w - width, x))
    y = max(0, min(cam_h - height, y))
    return CropBox(x=x, y=y, width=width, height=height)


def crop_for_panel(
    *,
    cam_w: int,
    cam_h: int,
    panel: CanvasRegion,
    face: FaceBox | None,
    zoom: float = 1.0,
    headroom: float = DEFAULT_HEADROOM,
) -> CropBox:
    """Crop a camera frame so the face fills a canvas panel."""

    aspect = panel.aspect
    crop_w = min(cam_w, cam_h * aspect) / max(1.0, float(zoom))
    crop_h = crop_w / aspect
    if crop_h > cam_h:
        crop_h = cam_h
        crop_w = crop_h * aspect
    focus_x = 0.5 if face is None else face.cx
    focus_y = 0.5 if face is None else face.cy
    return clamp_crop(
        focus_x=focus_x,
        focus_y=focus_y,
        crop_w=crop_w,
        crop_h=crop_h,
        cam_w=cam_w,
        cam_h=cam_h,
        headroom=headroom,
    )


def crop_for_text_face(
    *,
    cam_w: int,
    cam_h: int,
    face: FaceBox | None,
    zoom: float = 1.0,
    headroom: float = DEFAULT_HEADROOM,
) -> CropBox:
    return crop_for_panel(
        cam_w=cam_w,
        cam_h=cam_h,
        panel=LAYOUTS["FULL_FACE"].face,
        face=face,
        zoom=zoom,
        headroom=headroom,
    )


def upscale_ratio(crop_w: int, target_w: int = CANVAS_WIDTH) -> float:
    return round(float(target_w) / max(1, int(crop_w)), 4)


def low_resolution(crop_w: int, *, max_ratio: float = MAX_FACE_UPSCALE) -> bool:
    return upscale_ratio(crop_w) > max_ratio


def face_box_from_norm(
    bbox: dict[str, float] | FaceBox | None,
) -> FaceBox | None:
    if bbox is None:
        return None
    if isinstance(bbox, FaceBox):
        return bbox
    try:
        return FaceBox(
            cx=max(0.0, min(1.0, float(bbox["cx"]))),
            cy=max(0.0, min(1.0, float(bbox["cy"]))),
            w=min(1.0, max(0.001, float(bbox["w"]))),
            h=min(1.0, max(0.001, float(bbox["h"]))),
        )
    except (KeyError, TypeError, ValueError):
        return None


__all__ = [
    "CANVAS_HEIGHT",
    "CANVAS_WIDTH",
    "CONTENT_REGION",
    "DEFAULT_HEADROOM",
    "LAYOUTS",
    "MAX_FACE_UPSCALE",
    "SAFE_ZONES",
    "CanvasRegion",
    "CropBox",
    "FaceBox",
    "LayoutGeometry",
    "caption_region",
    "captions_are_safe",
    "clamp_crop",
    "crop_for_panel",
    "crop_for_text_face",
    "face_box_from_norm",
    "layout_geometry",
    "low_resolution",
    "subtitle_y_map",
    "upscale_ratio",
]
