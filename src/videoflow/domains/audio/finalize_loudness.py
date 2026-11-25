"""Exact loudness correction for the canonical audio bed."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from videoflow.runtime import find_binary

LOUDNESS_TOLERANCE = 0.6
CORRECTIVE_LIMITER = "alimiter=limit=-1.5dB"


def _ffmpeg() -> str:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise RuntimeError("FFmpeg is required for audio finalization")
    return str(binary)


def measure_integrated(path: Path) -> float:
    from videoflow.adapters.ffmpeg import FFmpegAdapter

    value = FFmpegAdapter().measure_loudness(path).get("integrated_lufs")
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -99.0


def correct_loudness(
    temp: Path,
    *,
    target_lufs: float,
    warnings: list[str],
) -> float:
    """Force the master inside ``target ± 0.6 LU`` with a linear correction."""

    measured = measure_integrated(temp)
    for _ in range(2):
        delta = float(target_lufs) - measured
        if abs(delta) <= LOUDNESS_TOLERANCE:
            break
        corrected = temp.with_name(f".{temp.stem}.correction.wav")
        corrected.unlink(missing_ok=True)
        completed = subprocess.run(
            [
                _ffmpeg(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(temp),
                "-af",
                f"volume={delta:.3f}dB,{CORRECTIVE_LIMITER}",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_s24le",
                str(corrected),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        if completed.returncode != 0 or not corrected.is_file():
            corrected.unlink(missing_ok=True)
            warnings.append(
                "loudness correction failed: "
                + (completed.stderr.strip()[-300:] or f"exit {completed.returncode}")
            )
            break
        os.replace(corrected, temp)
        measured = measure_integrated(temp)
        warnings.append(f"loudness corrected by {delta:+.2f} dB")
    return measured


__all__ = [
    "CORRECTIVE_LIMITER",
    "LOUDNESS_TOLERANCE",
    "correct_loudness",
    "measure_integrated",
]
