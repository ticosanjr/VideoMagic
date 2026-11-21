"""Decode/tonemap policy and source normalization decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.core.media_contract.validate import validate_media


def source_needs_normalization(path: str | Path) -> list[str]:
    """Return reasons the ingest stage must transcode the source."""

    report = validate_media(path, "source")
    video = report.metrics.get("video") or {}
    reasons: list[str] = []
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width and height and (width % 2 or height % 2):
        reasons.append("odd_dimensions")
    pix_fmt = str(video.get("pix_fmt") or "")
    if pix_fmt and pix_fmt not in {"yuv420p", "yuvj420p"}:
        reasons.append("pixel_format")
    transfer = str(video.get("color_transfer") or "")
    if transfer and transfer not in {"bt709", "smpte170m", "bt470bg", ""}:
        reasons.append("color_transfer")
    fps_num = int(video.get("fps_num") or 0)
    fps_den = int(video.get("fps_den") or 0)
    if fps_num and fps_den:
        fps = fps_num / fps_den
        if abs(fps - round(fps)) > 0.001 or round(fps) not in {24, 25, 30, 50, 60}:
            reasons.append("fps")
    return reasons


def color_profile(path: str | Path) -> dict[str, Any]:
    """Return the color metadata used to choose a decode/tonemap policy."""

    report = validate_media(path, "source")
    video = report.metrics.get("video") or {}
    transfer = str(video.get("color_transfer") or "")
    pix_fmt = str(video.get("pix_fmt") or "")
    ten_bit = "10le" in pix_fmt or "10be" in pix_fmt
    hdr = transfer in {"smpte2084", "arib-std-b67"}
    return {
        "ok": report.ok,
        "pix_fmt": pix_fmt,
        "color_transfer": transfer,
        "color_primaries": str(video.get("color_primaries") or ""),
        "color_space": str(video.get("color_space") or ""),
        "ten_bit": ten_bit,
        "hdr": hdr,
        "needs_cpu_decode": ten_bit or hdr or pix_fmt in {"yuv422p10le", "yuv420p10le"},
        "needs_tonemap": hdr,
    }
