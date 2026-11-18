"""Deterministic QA helpers for rendered video and speech."""

from __future__ import annotations

import difflib
import re
import subprocess
from pathlib import Path
from typing import Any

from videoflow.runtime import find_binary


def _run_filter(video: Path, filter_name: str) -> str:
    binary = find_binary("ffmpeg")
    if binary is None:
        return ""
    command = [
        binary,
        "-hide_banner",
        "-i",
        str(video),
        "-vf",
        filter_name,
        "-an",
        "-f",
        "null",
        "-",
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    return completed.stderr


def detect_black(video: Path, *, min_duration: float = 0.15) -> list[dict[str, Any]]:
    text = _run_filter(
        video, f"blackdetect=d={max(0.01, min_duration):.3f}:pix_th=0.10"
    )
    issues: list[dict[str, Any]] = []
    pattern = re.compile(
        r"black_start:(?P<start>[0-9.]+)\s+black_end:(?P<end>[0-9.]+)"
    )
    for match in pattern.finditer(text):
        start = float(match.group("start"))
        end = float(match.group("end"))
        issues.append(
            {
                "kind": "black_frame",
                "severity": "critical",
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "message": "Black or near-black frame span.",
            }
        )
    return issues


def detect_freeze(video: Path, *, min_duration: float = 1.0) -> list[dict[str, Any]]:
    text = _run_filter(
        video, f"freezedetect=n=0.001:d={max(0.1, min_duration):.3f}"
    )
    issues: list[dict[str, Any]] = []
    start: float | None = None
    for line in text.splitlines():
        if "freeze_start:" in line:
            try:
                start = float(line.split("freeze_start:", 1)[1].strip())
            except ValueError:
                start = None
        elif "freeze_end:" in line and start is not None:
            try:
                end = float(line.split("freeze_end:", 1)[1].strip())
            except ValueError:
                end = start
            issues.append(
                {
                    "kind": "static_screen",
                    "severity": "warning",
                    "start_sec": round(start, 3),
                    "end_sec": round(end, 3),
                    "message": "Static frame span longer than expected.",
                }
            )
            start = None
    return issues


def words(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-zÀ-ÿ']+", text.casefold())


def compare_text(reference: str, hypothesis: str) -> dict[str, Any]:
    source = words(reference)
    spoken = words(hypothesis)
    matcher = difflib.SequenceMatcher(a=source, b=spoken, autojunk=False)
    ratio = matcher.ratio()
    missing: list[str] = []
    extra: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {"delete", "replace"}:
            missing.extend(source[i1:i2])
        if tag in {"insert", "replace"}:
            extra.extend(spoken[j1:j2])
    return {
        "similarity": round(ratio, 4),
        "reference_words": len(source),
        "spoken_words": len(spoken),
        "missing": missing[:80],
        "extra": extra[:80],
        "passed": ratio >= 0.90,
    }


def detect_audio_silence(
    media: Path,
    *,
    threshold_db: float = -40.0,
    min_duration: float = 0.3,
) -> list[dict[str, Any]]:
    """Detect silent spans in the final deliverable audio track."""

    binary = find_binary("ffmpeg")
    if binary is None:
        return []
    completed = subprocess.run(
        [
            binary,
            "-hide_banner",
            "-i",
            str(media),
            "-af",
            f"silencedetect=noise={threshold_db}dB:d={min_duration:.3f}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    issues: list[dict[str, Any]] = []
    start: float | None = None
    for line in completed.stderr.splitlines():
        if "silence_start:" in line:
            try:
                start = float(line.split("silence_start:", 1)[1].strip())
            except ValueError:
                start = None
        elif "silence_end:" in line and start is not None:
            try:
                end = float(line.split("silence_end:", 1)[1].split("|", 1)[0].strip())
            except ValueError:
                end = start
            issues.append(
                {
                    "kind": "audio_silence",
                    "severity": "warning",
                    "start_sec": round(start, 3),
                    "end_sec": round(end, 3),
                    "duration_sec": round(max(0.0, end - start), 3),
                    "message": "Silent audio span.",
                }
            )
            start = None
    return issues


def render_waveform(
    media: Path, target: Path, *, width: int = 1600, height: int = 240
) -> Path | None:
    binary = find_binary("ffmpeg")
    if binary is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(media),
            "-filter_complex",
            f"[0:a]showwavespic=s={width}x{height}:colors=white[w]",
            "-map",
            "[w]",
            "-frames:v",
            "1",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    return target if completed.returncode == 0 and target.is_file() else None
