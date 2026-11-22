"""Kdenlive helper: shared MLT primitives."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from videoflow.domain.timebase import Rounding


def _property(parent: ET.Element, name: str, value: str) -> None:
    ET.SubElement(parent, "property", {"name": name}).text = value

def _timecode(frame: int, fps_num: int, fps_den: int) -> str:
    total_ms = round(max(0, frame) * fps_den * 1000 / fps_num)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

def _transform_rect(
    media,
    scale: float,
    pos_x: float,
    pos_y: float,
    anchor: str,
    pan_direction: str,
    opacity: float,
) -> tuple[int, int, int, int, float]:
    width = round(media.width * scale)
    height = round(media.height * scale)
    x = round((media.width - width) / 2 + pos_x * media.width)
    y = round((media.height - height) / 2 + pos_y * media.height)
    if anchor == "upper_third":
        y -= round((height - media.height) / 3)
    if pan_direction == "left_to_right":
        x -= media.width // 12
    elif pan_direction == "right_to_left":
        x += media.width // 12
    return x, y, width, height, opacity

def _append_volume_fade(
    entry: ET.Element,
    clip,
    media,
    duration_frames: int,
    *,
    previous_transition=None,
    current_transition=None,
) -> None:
    fade_in = media.timebase().sample_to_frame(clip.fade_in_samples, Rounding.CEIL)
    fade_out = media.timebase().sample_to_frame(clip.fade_out_samples, Rounding.CEIL)
    if previous_transition is not None and previous_transition.audio:
        fade_in = max(fade_in, previous_transition.duration_frames)
    if current_transition is not None and current_transition.audio:
        fade_out = max(fade_out, current_transition.duration_frames)
    if fade_in <= 0 and fade_out <= 0:
        return
    fade_in = min(fade_in, max(0, duration_frames - 1))
    fade_out = min(fade_out, max(0, duration_frames - 1))
    points: list[tuple[int, int]] = []
    if fade_in > 0:
        points.extend([(0, -60), (fade_in, 0)])
    else:
        points.append((0, 0))
    if fade_out > 0:
        points.append((max(0, duration_frames - 1 - fade_out), 0))
        points.append((max(0, duration_frames - 1), -60))
    level = ";".join(f"{frame}={value}" for frame, value in points)
    filter_element = ET.SubElement(
        entry,
        "filter",
        {
            "id": f"filter-{clip.clip_id}",
            "in": _timecode(0, media.fps_num, media.fps_den),
            "out": _timecode(max(0, duration_frames - 1), media.fps_num, media.fps_den),
        },
    )
    _property(filter_element, "window", "75")
    _property(filter_element, "max_gain", "20dB")
    _property(filter_element, "mlt_service", "volume")
    _property(filter_element, "kdenlive_id", "volume")
    _property(filter_element, "level", level)
