"""ffprobe payload helpers for audio/video metrics."""

from __future__ import annotations

from typing import Any


def _stream(payload: dict[str, Any], kind: str) -> dict[str, Any]:
    for stream in payload.get("streams") or []:
        if isinstance(stream, dict) and stream.get("codec_type") == kind:
            return stream
    return {}


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _fps(stream: dict[str, Any]) -> tuple[int, int] | None:
    raw = str(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "")
    if not raw or raw in {"0/0", "N/A"}:
        return None
    left, _, right = raw.partition("/")
    try:
        num = int(left)
        den = int(right or "1")
    except ValueError:
        return None
    if num <= 0 or den <= 0:
        return None
    return num, den


def _bit_rate(stream: dict[str, Any]) -> int | None:
    direct = _int(stream.get("bit_rate"))
    if direct:
        return direct
    tags = stream.get("tags")
    if isinstance(tags, dict):
        return _int(tags.get("BPS"))
    return None


def _audio_metrics(stream: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_rate": _int(stream.get("sample_rate")),
        "channels": _int(stream.get("channels")),
        "codec": str(stream.get("codec_name") or ""),
        "bit_rate": _bit_rate(stream),
        "duration_sec": _float(stream.get("duration")),
    }


def _video_metrics(stream: dict[str, Any]) -> dict[str, Any]:
    fps = _fps(stream)
    return {
        "width": _int(stream.get("width")),
        "height": _int(stream.get("height")),
        "fps_num": fps[0] if fps else None,
        "fps_den": fps[1] if fps else None,
        "fps": round(fps[0] / fps[1], 6) if fps else None,
        "pix_fmt": str(stream.get("pix_fmt") or ""),
        "alpha_mode": str((stream.get("tags") or {}).get("alpha_mode") or ""),
        "codec": str(stream.get("codec_name") or ""),
        "color_transfer": str(stream.get("color_transfer") or ""),
        "color_primaries": str(stream.get("color_primaries") or ""),
        "color_space": str(stream.get("color_space") or ""),
        "bits_per_raw_sample": _int(stream.get("bits_per_raw_sample")),
        "duration_sec": _float(stream.get("duration")),
        "nb_frames": _int(stream.get("nb_read_frames")) or _int(stream.get("nb_frames")),
    }

