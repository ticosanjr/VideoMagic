"""Post-render duration and frame integrity checks for MP4 delivery."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from videoflow.domain.errors import ExportError
from videoflow.runtime import find_binary

CONTAINER_FALLBACK_SEC = 0.10


@dataclass(slots=True)
class IntegrityReport:
    ok: bool
    expected_sec: float = 0.0
    expected_frames: int = 0
    expected_samples: int = 0
    format_sec: float | None = None
    video_sec: float | None = None
    audio_sec: float | None = None
    frame_count: int | None = None
    last_sentence_end_sec: float | None = None
    deltas: dict[str, float] = field(default_factory=dict)
    criteria: dict[str, bool] = field(default_factory=dict)
    reason: str = ""
    container_fallback_used: bool = False
    streams: dict[str, Any] = field(default_factory=dict)

    @property
    def frame_delta(self) -> int | None:
        if self.frame_count is None or not self.expected_frames:
            return None
        return self.frame_count - self.expected_frames

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "expected_sec": round(self.expected_sec, 6),
            "expected_frames": self.expected_frames,
            "expected_samples": self.expected_samples,
            "format_sec": self.format_sec,
            "video_sec": self.video_sec,
            "audio_sec": self.audio_sec,
            "frame_count": self.frame_count,
            "frame_delta": self.frame_delta,
            "last_sentence_end_sec": self.last_sentence_end_sec,
            "deltas": {key: round(value, 6) for key, value in self.deltas.items()},
            "criteria": dict(self.criteria),
            "reason": self.reason,
            "container_fallback_used": self.container_fallback_used,
        }


def probe_media(path: Path, *, count_frames: bool = True) -> dict[str, Any]:
    """Return format and stream metadata, optionally with a real frame count."""

    binary = find_binary("ffprobe")
    if binary is None:
        raise ExportError("ffprobe is required for the export integrity gate")
    command = [binary, "-v", "error"]
    if count_frames:
        command.append("-count_frames")
    command.extend(
        [
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(Path(path).expanduser()),
        ]
    )
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
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
    return payload if isinstance(payload, dict) else {}


def _seconds(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _integer(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _first_stream(payload: dict[str, Any], kind: str) -> dict[str, Any]:
    for stream in payload.get("streams") or []:
        if isinstance(stream, dict) and stream.get("codec_type") == kind:
            return stream
    return {}


def probe_durations(path: Path) -> tuple[float | None, float | None, float | None]:
    """Return ``(format, first video, first audio)`` durations in seconds."""

    payload = probe_media(path)
    return (
        _seconds((payload.get("format") or {}).get("duration")),
        _seconds(_first_stream(payload, "video").get("duration")),
        _seconds(_first_stream(payload, "audio").get("duration")),
    )


def validate_integrity(
    path: Path,
    expected_sec: float,
    *,
    expected_frames: int = 0,
    expected_samples: int = 0,
    fps: float = 0.0,
    last_sentence_end_sec: float | None = None,
    tolerance_frames: int = 1,
    container_fallback: bool = True,
) -> IntegrityReport:
    """Validate final delivery against timeline duration, frames, and speech tail."""

    payload = probe_media(path)
    expected = max(0.0, float(expected_sec))
    base_tolerance = (1.0 / fps) if fps > 0 else 0.001
    frame_tolerance = max(base_tolerance, base_tolerance * max(1, int(tolerance_frames)))
    audio_tolerance = max(frame_tolerance, 0.045)
    format_sec = _seconds((payload.get("format") or {}).get("duration"))
    video = _first_stream(payload, "video")
    audio = _first_stream(payload, "audio")
    video_sec = _seconds(video.get("duration"))
    audio_sec = _seconds(audio.get("duration"))
    frame_count = _integer(video.get("nb_read_frames")) or _integer(video.get("nb_frames"))
    deltas: dict[str, float] = {}
    for name, value in (("format", format_sec), ("video", video_sec), ("audio", audio_sec)):
        if value is not None:
            deltas[name] = value - expected
    criteria: dict[str, bool] = {}
    reasons: list[str] = []
    for name in ("video", "audio"):
        value = video_sec if name == "video" else audio_sec
        if value is None:
            continue
        tolerance = audio_tolerance if name == "audio" else frame_tolerance
        passed = abs(value - expected) <= tolerance + 1e-6
        criteria[f"{name}_duration"] = passed
        if not passed:
            reasons.append(f"{name} duration drift {value - expected:+.6f}s > 1 frame")
    if format_sec is not None:
        format_passed = abs(format_sec - expected) <= frame_tolerance + 1e-6
        if (
            not format_passed
            and container_fallback
            and abs(format_sec - expected) <= CONTAINER_FALLBACK_SEC + 1e-6
        ):
            format_passed = True
            report_fallback = True
        else:
            report_fallback = False
        criteria["format_duration"] = format_passed
        if not format_passed:
            reasons.append(f"format duration drift {format_sec - expected:+.6f}s")
    else:
        report_fallback = False
    if expected_frames > 0 and frame_count is not None:
        frames_passed = abs(frame_count - expected_frames) <= max(0, int(tolerance_frames))
        criteria["frame_count"] = frames_passed
        if not frames_passed:
            reasons.append(
                f"frame count {frame_count} != expected {expected_frames}"
            )
    if last_sentence_end_sec is not None and expected > 0:
        tail_ok = expected + 1e-6 >= float(last_sentence_end_sec)
        criteria["last_sentence"] = tail_ok
        if not tail_ok:
            reasons.append(
                "last sentence end is beyond the rendered duration "
                f"({last_sentence_end_sec:.6f}s > {expected:.6f}s)"
            )
    ok = not reasons
    return IntegrityReport(
        ok=ok,
        expected_sec=expected,
        expected_frames=max(0, int(expected_frames)),
        expected_samples=max(0, int(expected_samples)),
        format_sec=format_sec,
        video_sec=video_sec,
        audio_sec=audio_sec,
        frame_count=frame_count,
        last_sentence_end_sec=last_sentence_end_sec,
        deltas=deltas,
        criteria=criteria,
        reason="; ".join(reasons),
        container_fallback_used=bool(report_fallback),
        streams={"format": format_sec, "video": video_sec, "audio": audio_sec},
    )


def validate_duration(
    path: Path,
    expected_sec: float,
    *,
    tolerance: float = CONTAINER_FALLBACK_SEC,
) -> IntegrityReport:
    """Compare container/stream durations against a target."""

    format_sec, video_sec, audio_sec = probe_durations(path)
    expected = max(0.0, float(expected_sec))
    values = {"format": format_sec, "video": video_sec, "audio": audio_sec}
    deltas = {
        name: value - expected
        for name, value in values.items()
        if value is not None
    }
    bad = [name for name, delta in deltas.items() if abs(delta) > tolerance]
    return IntegrityReport(
        ok=not bad,
        expected_sec=expected,
        format_sec=format_sec,
        video_sec=video_sec,
        audio_sec=audio_sec,
        deltas=deltas,
        criteria={name: name not in bad for name in deltas},
        reason="" if not bad else f"duration drift beyond {tolerance:.2f}s: {', '.join(bad)}",
        streams={"format": format_sec, "video": video_sec, "audio": audio_sec},
    )


def validate_or_raise(
    path: Path,
    expected_sec: float,
    *,
    expected_frames: int = 0,
    expected_samples: int = 0,
    fps: float = 0.0,
    last_sentence_end_sec: float | None = None,
) -> IntegrityReport:
    report = validate_integrity(
        path,
        expected_sec,
        expected_frames=expected_frames,
        expected_samples=expected_samples,
        fps=fps,
        last_sentence_end_sec=last_sentence_end_sec,
    )
    if not report.ok:
        raise ExportError(f"{Path(path).name} failed the integrity gate: {report.reason}")
    return report


__all__ = [
    "CONTAINER_FALLBACK_SEC",
    "IntegrityReport",
    "probe_durations",
    "probe_media",
    "validate_duration",
    "validate_integrity",
    "validate_or_raise",
]
