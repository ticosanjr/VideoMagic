"""Audio contract: RMS, mono repair, and PCM length invariants."""

from __future__ import annotations

import array
import math
import shutil
import subprocess
from pathlib import Path

from videoflow.core.media_contract.constants import AUDIO_MASTER_RATE
from videoflow.core.media_contract.models import MediaContractError
from videoflow.runtime import find_binary


def channel_rms(path: str | Path, *, seconds: float = 8.0) -> tuple[float, float]:
    """Return per-channel RMS in dBFS for the first ``seconds`` of a stereo file."""

    ffmpeg = find_binary("ffmpeg")
    if ffmpeg is None:
        return -120.0, -120.0
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-t",
            f"{max(0.1, seconds):.3f}",
            "-i",
            str(Path(path).expanduser()),
            "-f",
            "s16le",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-",
        ],
        capture_output=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0 or not completed.stdout:
        return -120.0, -120.0
    samples = array.array("h")
    samples.frombytes(completed.stdout)
    left = samples[0::2]
    right = samples[1::2]
    if not left or not right:
        return -120.0, -120.0

    def rms(values: array.array) -> float:
        if not values:
            return -120.0
        total = sum(float(value) * float(value) for value in values)
        return 20.0 * math.log10(max(1e-12, math.sqrt(total / len(values)) / 32768.0))

    return rms(left), rms(right)


def needs_mono_repair(left_db: float, right_db: float, *, threshold_db: float = 18.0) -> str:
    """Return ``left``/``right`` when one channel is effectively silent."""

    if left_db <= -90.0 and right_db <= -90.0:
        return ""
    if abs(left_db - right_db) <= threshold_db:
        return ""
    return "left" if left_db > right_db else "right"


def repair_mono_file(
    path: str | Path,
    *,
    threshold_db: float = 18.0,
    sample_rate: int = AUDIO_MASTER_RATE,
) -> bool:
    """Rewrite a unilateral stereo file as centered dual-mono.

    Returns ``True`` when a repair was applied. The file is replaced atomically.
    """

    source = Path(path).expanduser()
    if not source.is_file():
        return False
    repair = needs_mono_repair(*channel_rms(source), threshold_db=threshold_db)
    if not repair:
        return False
    ffmpeg = find_binary("ffmpeg")
    if ffmpeg is None:
        raise MediaContractError("ffmpeg_missing", "FFmpeg is required for mono repair")
    temporary = source.with_name(f".{source.name}.mono-repair{source.suffix}")
    pan = "pan=stereo|c0=c0|c1=c0" if repair == "left" else "pan=stereo|c0=c1|c1=c1"
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-af",
            f"{pan},aformat=sample_fmts=fltp:channel_layouts=stereo",
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            str(temporary),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0 or not temporary.is_file():
        temporary.unlink(missing_ok=True)
        raise MediaContractError(
            "mono_repair_failed",
            "mono repair failed: " + (completed.stderr.strip()[-300:] or "no output"),
            path=str(source),
        )
    shutil.move(str(temporary), str(source))
    return True


def assert_pcm_buffer(
    pcm: bytes | bytearray | memoryview,
    expected_samples: int,
    channels: int,
    bytes_per_sample: int,
) -> None:
    """Fail when a rendered PCM buffer does not match the timeline."""

    expected = int(expected_samples) * int(channels) * int(bytes_per_sample)
    actual = len(pcm)
    if actual != expected:
        raise MediaContractError(
            "audio_length_mismatch",
            f"PCM buffer has {actual} bytes, expected {expected}",
        )
