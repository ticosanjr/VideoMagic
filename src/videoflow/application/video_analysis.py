"""Scene-change detection for multimodal Short curation."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from videoflow.domain.errors import IngestError
from videoflow.runtime import find_binary

_SCENE_TIME = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def parse_scene_times(log: str) -> list[float]:
    return sorted({float(match.group(1)) for match in _SCENE_TIME.finditer(log)})


def detect_scene_changes(
    source: Path,
    *,
    threshold: float = 0.3,
    timeout: float = 300.0,
) -> list[float]:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise IngestError("FFmpeg is not available for scene analysis.")
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "info",
        "-i",
        str(Path(source).expanduser()),
        "-vf",
        f"select='gt(scene,{max(0.01, min(1.0, threshold))})',showinfo",
        "-an",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IngestError(f"Scene analysis failed: {exc}") from exc
    if result.returncode != 0:
        raise IngestError("Scene analysis failed.")
    return parse_scene_times(result.stderr)


def scene_intervals(
    times: list[float],
    *,
    sample_rate: int,
    window_sec: float = 0.5,
) -> list[tuple[int, int]]:
    if sample_rate <= 0:
        return []
    window = max(1, round(sample_rate * max(0.1, window_sec)))
    intervals: list[tuple[int, int]] = []
    for time in times:
        center = round(time * sample_rate)
        intervals.append((max(0, center - window), center + window))
    return intervals
