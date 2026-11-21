"""Audio extraction, loudness, speech, and voiceover."""

# ruff: noqa: F401


import contextlib
import hashlib
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import uuid4

from videoflow.adapters.ffmpeg.helpers import (
    _complement,
    _crop_expression,
    _cutout_graph,
    _filter_path,
    _filter_script_args,
    _first_stream,
    _frame_count,
    _frame_rate,
    _piece_focus,
    _piece_keyframes,
    _rate_value,
    _require_int,
    _seconds_to_samples,
    parse_silence,
)
from videoflow.application.music import music_filter
from videoflow.domain.errors import IngestError, JobCancelledError
from videoflow.domain.state import MediaInfo
from videoflow.domain.timebase import Rounding, Timebase
from videoflow.runtime import find_binary

DEFAULT_TIMEOUT_SECONDS = 600

DEFAULT_RENDER_TIMEOUT_SECONDS = 3600

_SILENCE_START = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")




class AudioMixin:
    def extract_pcm(
        self,
        source: Path,
        destination: Path,
        *,
        sample_rate: int = 16000,
    ) -> Path:
        source_path = Path(source).expanduser()
        if not source_path.is_file():
            raise IngestError(f"Source does not exist: {source_path}")
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f"{target.stem}.part.wav")
        self._run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-c:a",
                "pcm_s16le",
                "-f",
                "wav",
                str(temp),
            ]
        )
        temp.replace(target)
        return target

    def measure_loudness(self, source: Path) -> dict[str, float]:
        """Return EBU R128 integrated loudness and true peak for a media file."""

        source_path = Path(source).expanduser()
        if not source_path.is_file():
            raise IngestError(f"Media does not exist: {source_path}")
        _, stderr = self._capture(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-i",
                str(source_path),
                "-af",
                "ebur128=peak=true",
                "-f",
                "null",
                "-",
            ],
            timeout=1800,
        )
        integrated = [float(match) for match in re.findall(r"I:\s*(-?[0-9.]+)\s*LUFS", stderr)]
        peaks = [float(match) for match in re.findall(r"Peak:\s*(-?[0-9.]+)\s*dBFS", stderr)]
        if not integrated:
            raise IngestError("Could not measure loudness.")
        return {
            "integrated_lufs": integrated[-1],
            "true_peak_dbfs": peaks[-1] if peaks else 0.0,
        }

    def master_audio(
        self,
        source: Path,
        destination: Path,
        *,
        filters: Sequence[str] = (),
        sample_rate: int = 48000,
    ) -> Path:
        """Render the dialogue bed with a deterministic audio filter chain."""

        source_path = Path(source).expanduser()
        if not source_path.is_file():
            raise IngestError(f"Source does not exist: {source_path}")
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f"{target.stem}.part.wav")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        command.extend(
            ["-i", str(source_path), "-vn", "-ac", "2", "-ar", str(sample_rate)]
        )
        chain = ",".join(item for item in filters if item)
        if chain:
            command.extend(["-af", chain])
        command.extend(["-c:a", "pcm_s16le", "-f", "wav", str(temp)])
        self._run(command)
        temp.replace(target)
        return target

    def pcm_digest(self, path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def detect_speech(
        self,
        wav_path: Path,
        *,
        duration_samples: int,
        sample_rate: int,
        noise_db: float = -30.0,
        min_silence_ms: int = 400,
        min_speech_ms: int = 100,
    ) -> list[tuple[int, int]]:
        """Detect speech with FFmpeg ``silencedetect``.

        This is the portable, model-free engine. It is less accurate than Silero
        but needs nothing beyond FFmpeg.
        """

        source = Path(wav_path).expanduser()
        if not source.is_file():
            raise IngestError(f"Audio does not exist: {source}")
        if duration_samples <= 0 or sample_rate <= 0:
            raise IngestError("duration and sample rate must be positive")
        args = [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(source),
            "-af",
            f"silencedetect=noise={noise_db:g}dB:d={min_silence_ms / 1000:g}",
            "-f",
            "null",
            "-",
        ]
        _, stderr = self._capture(args)
        silence = parse_silence(stderr, duration_samples, sample_rate)
        minimum = max(1, (min_speech_ms * sample_rate + 500) // 1000)
        return [
            (start, end)
            for start, end in _complement(silence, duration_samples)
            if end - start >= minimum
        ]

    def mix_voiceover(
        self,
        short_path: Path,
        voice_path: Path,
        destination: Path,
        *,
        duration_sec: float,
        voice_volume: float = 1.0,
        original_volume: float = 0.35,
    ) -> Path:
        """Mix a voice-over track over an existing Short MP4."""

        source = Path(short_path).expanduser()
        voice = Path(voice_path).expanduser()
        target = Path(destination).expanduser()
        duration = max(0.01, duration_sec)
        target.parent.mkdir(parents=True, exist_ok=True)
        filter_complex = (
            f"[0:a]volume={max(0.0, min(1.0, original_volume))}[orig];"
            f"[1:a]atrim=0:{duration:.3f},volume={max(0.0, min(1.0, voice_volume))}[vo];"
            "[orig][vo]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )
        self._capture(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-i",
                str(voice),
                "-filter_complex",
                filter_complex,
                "-map",
                "0:v",
                "-map",
                "[a]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-t",
                f"{duration:.6f}",
                "-movflags",
                "+faststart",
                str(target),
            ]
        )
        return target

    def _attach_cards(
        self,
        source: Path,
        *,
        width: int,
        height: int,
        intro_path: Path | None,
        outro_path: Path | None,
        intro_duration: float,
        outro_duration: float,
        work: Path,
        fps: int = 30,
    ) -> Path:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
        ]
        filters: list[str] = []
        labels: list[str] = []
        filters.append(
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={max(1, int(fps))},"
            "setpts=PTS-STARTPTS[v0]"
        )
        filters.append(
            "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a0]"
        )
        labels.extend(["[v0]", "[a0]"])
        index = 1
        segments: list[tuple[Path, float]] = []
        if intro_path is not None:
            segments.append((Path(intro_path), max(0.2, intro_duration)))
        segments.append((Path(source), 0.0))
        if outro_path is not None:
            segments.append((Path(outro_path), max(0.2, outro_duration)))
        # The source is input 0; cards are added after it.
        for path, duration in segments:
            if path == Path(source):
                continue
            image_card = path.suffix.casefold() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            }
            command.extend(
                (["-loop", "1"] if image_card else ["-t", f"{duration:.3f}"])
                + ["-i", str(path)]
            )
            video_index = index
            audio_index = index + 1
            command.extend(
                [
                    "-f",
                    "lavfi",
                    "-t",
                    f"{duration:.3f}",
                    "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                ]
            )
            filters.append(
                f"[{video_index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,fps={max(1, int(fps))},"
                f"trim=duration={duration:.3f},setpts=PTS-STARTPTS[v{index}]"
            )
            filters.append(
                f"[{audio_index}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS[a{index}]"
            )
            labels.extend([f"[v{index}]", f"[a{index}]"])
            index += 2
        # Rebuild in intro/source/outro order with labels by segment.
        ordered: list[str] = []
        cursor = 1
        if intro_path is not None:
            ordered.extend([f"[v{cursor}]", f"[a{cursor}]"])
            cursor += 2
        ordered.extend(["[v0]", "[a0]"])
        if outro_path is not None:
            ordered.extend([f"[v{cursor}]", f"[a{cursor}]"])
        filters.append("".join(ordered) + f"concat=n={len(ordered) // 2}:v=1:a=1[v][a]")
        output = work / "cards.mp4"
        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-r",
                str(max(1, int(fps))),
                "-fps_mode",
                "cfr",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        self._capture(command)
        return output

