"""Cheap audio/color diagnosis returned by ingest."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.core.media_contract import color_profile, validate_media
from videoflow.domains.audio.finalize import _channel_rms, _needs_mono_repair


def diagnose_audio(source: str | Path, media: Any | None = None) -> dict[str, Any]:
    path = Path(source).expanduser()
    report = validate_media(path, "source")
    audio = report.metrics.get("audio") or {}
    video = report.metrics.get("video") or {}
    left_db, right_db = _channel_rms(path, seconds=5.0)
    repair = _needs_mono_repair(left_db, right_db)
    fps_num = video.get("fps_num")
    fps_den = video.get("fps_den")
    fps = None
    fractional = False
    if fps_num and fps_den:
        fps = round(float(fps_num) / float(fps_den), 6)
        fractional = abs(fps - round(fps)) > 1e-6
    profile = color_profile(path)
    return {
        "ok": report.ok,
        "source": str(path),
        "sample_rate": audio.get("sample_rate"),
        "channels": audio.get("channels"),
        "codec": audio.get("codec") or "",
        "left_rms_db": round(left_db, 2),
        "right_rms_db": round(right_db, 2),
        "mono_left_only": repair == "left",
        "mono_right_only": repair == "right",
        "mono_repair_recommended": bool(repair),
        "mono_repaired": False,
        "fps": fps,
        "fps_fractional": fractional,
        "color": profile,
        "errors": report.errors,
        "warnings": report.warnings,
    }


__all__ = ["diagnose_audio"]
