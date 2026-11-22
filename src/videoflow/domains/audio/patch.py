"""Surgical audio replacement with crossfades."""

from __future__ import annotations

import subprocess
from pathlib import Path

from videoflow.runtime import find_binary


def _duration(path: Path) -> float:
    binary = find_binary("ffprobe")
    if binary is None:
        return 0.0
    completed = subprocess.run(
        [
            binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return max(0.0, float(completed.stdout.strip()))
    except ValueError:
        return 0.0


def patch_audio(
    master: Path,
    replacement: Path,
    *,
    start_sec: float,
    end_sec: float,
    output: Path,
    crossfade_ms: int = 80,
    sample_rate: int = 48000,
) -> dict[str, object]:
    """Replace ``[start_sec, end_sec]`` in master with a synthesized clip."""

    source = Path(master).expanduser()
    patch = Path(replacement).expanduser()
    target = Path(output).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"master audio not found: {source}")
    if not patch.is_file():
        raise FileNotFoundError(f"replacement audio not found: {patch}")
    if end_sec <= start_sec:
        raise ValueError("end_sec must be greater than start_sec")
    binary = find_binary("ffmpeg")
    if binary is None:
        raise RuntimeError("FFmpeg is required for audio patching")
    duration = _duration(patch)
    fade = min(max(0.0, crossfade_ms / 1000.0), max(0.0, duration / 2))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.stem}.part{target.suffix}")
    patch_chain = f"[1:a]aresample={sample_rate},aformat=channel_layouts=mono"
    if fade > 0 and duration > 0:
        patch_chain += (
            f",afade=t=in:st=0:d={fade:.3f}"
            f",afade=t=out:st={max(0.0, duration - fade):.3f}:d={fade:.3f}"
        )
    patch_chain += "[patch]"
    filter_complex = (
        f"[0:a]atrim=start=0:end={start_sec:.3f},asetpts=PTS-STARTPTS[a0];"
        f"[0:a]atrim=start={end_sec:.3f},asetpts=PTS-STARTPTS[a2];"
        f"{patch_chain};"
        "[a0][patch][a2]concat=n=3:v=0:a=1[out]"
    )
    completed = subprocess.run(
        [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-i",
            str(patch),
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(temporary),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        temporal = temporary
        temporal.unlink(missing_ok=True)
        raise RuntimeError(f"audio patch failed: {completed.stderr.strip()[-800:]}")
    temporary.replace(target)
    return {
        "path": str(target),
        "start_sec": start_sec,
        "end_sec": end_sec,
        "replacement_sec": round(duration, 3),
        "crossfade_ms": crossfade_ms,
    }
