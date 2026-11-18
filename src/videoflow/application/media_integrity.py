"""Post-render duration integrity checks for MP4 delivery."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from videoflow.domain.errors import ExportError
from videoflow.runtime import find_binary

DURATION_TOLERANCE_SEC = 0.10


@dataclass(slots=True)
class DurationReport:
    ok: bool
    expected_sec: float = 0.0
    format_sec: float | None = None
    video_sec: float | None = None
    audio_sec: float | None = None
    deltas: dict[str, float] = field(default_factory=dict)
    reason: str = ""
    streams: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "expected_sec": round(self.expected_sec, 6),
            "format_sec": self.format_sec,
            "video_sec": self.video_sec,
            "audio_sec": self.audio_sec,
            "deltas": {key: round(value, 6) for key, value in self.deltas.items()},
            "reason": self.reason,
        }


def probe_durations(path: Path) -> tuple[float | None, float | None, float | None]:
    """Return ``(format, first video, first audio)`` durations in seconds."""

    binary = find_binary("ffprobe")
    if binary is None:
        raise ExportError("ffprobe is required for the export duration gate")
    completed = subprocess.run(
        [
            binary,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(Path(path).expanduser()),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        raise ExportError(
            "ffprobe could not read the rendered file: "
            + (completed.stderr.strip()[-400:] or f"exit {completed.returncode}")
        )
    try:
        payload = json.loads(completed.stdout or "{}")
    except ValueError as exc:
        raise ExportError("ffprobe returned invalid JSON") from exc
    format_sec = _seconds((payload.get("format") or {}).get("duration"))
    video_sec = audio_sec = None
    for stream in payload.get("streams") or []:
        if stream.get("codec_type") == "video" and video_sec is None:
            video_sec = _seconds(stream.get("duration"))
        elif stream.get("codec_type") == "audio" and audio_sec is None:
            audio_sec = _seconds(stream.get("duration"))
    return format_sec, video_sec, audio_sec


def _seconds(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def validate_duration(
    path: Path,
    expected_sec: float,
    *,
    tolerance: float = DURATION_TOLERANCE_SEC,
) -> DurationReport:
    """Compare format and stream durations against the timeline expectation."""

    format_sec, video_sec, audio_sec = probe_durations(path)
    expected = max(0.0, float(expected_sec))
    values = {
        "format": format_sec,
        "video": video_sec,
        "audio": audio_sec,
    }
    deltas: dict[str, float] = {}
    for name, value in values.items():
        if value is None:
            continue
        deltas[name] = value - expected
    bad = [name for name, delta in deltas.items() if abs(delta) > tolerance]
    ok = not bad
    reason = "" if ok else f"duration drift beyond {tolerance:.2f}s: {', '.join(bad)}"
    return DurationReport(
        ok=ok,
        expected_sec=expected,
        format_sec=format_sec,
        video_sec=video_sec,
        audio_sec=audio_sec,
        deltas=deltas,
        reason=reason,
        streams={"format": format_sec, "video": video_sec, "audio": audio_sec},
    )


def validate_or_raise(
    path: Path,
    expected_sec: float,
    *,
    tolerance: float = DURATION_TOLERANCE_SEC,
) -> DurationReport:
    report = validate_duration(path, expected_sec, tolerance=tolerance)
    if not report.ok:
        raise ExportError(f"{Path(path).name} failed the duration gate: {report.reason}")
    return report


__all__ = [
    "DURATION_TOLERANCE_SEC",
    "DurationReport",
    "probe_durations",
    "validate_duration",
    "validate_or_raise",
]
