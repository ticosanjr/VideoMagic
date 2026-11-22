"""Sample-exact PCM repair for the final audio bed."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from videoflow.runtime import find_binary


def _ffmpeg() -> str:
    binary = find_binary("ffmpeg")
    if binary is None:
        from videoflow.domain.errors import ExportError

        raise ExportError("ffmpeg is required for audio finalization")
    return binary


def pad_to_duration(path: Path, duration: float) -> None:
    """Re-pad/trim a WAV so its length is sample-exact at 48 kHz.

    ``loudnorm`` upsamples internally and can shave a couple of frames from the
    tail. This second pass uses ``atrim=end_sample`` so the master matches the
    video timeline exactly.
    """

    target = Path(path)
    exact = target.with_name(f".{target.stem}.exact.wav")
    sample_count = int(round(float(duration) * 48_000))
    completed = subprocess.run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(target),
            "-af",
            f"apad=whole_dur={float(duration):.6f},atrim=end_sample={sample_count}",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            str(exact),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    if completed.returncode == 0 and exact.is_file():
        os.replace(exact, target)
    else:
        exact.unlink(missing_ok=True)
