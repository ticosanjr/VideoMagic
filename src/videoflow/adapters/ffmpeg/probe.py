"""Probe, CFR normalization, and proxy generation."""

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




class ProbeMixin:
    def probe(self, path: Path) -> MediaInfo:
        source = Path(path).expanduser()
        if not source.is_file():
            raise IngestError(f"Source does not exist: {source}")
        payload = self._run_json(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(source),
            ]
        )
        streams = payload.get("streams") or []
        video = _first_stream(streams, "video", skip_attached_picture=True)
        audio = _first_stream(streams, "audio")
        if video is None:
            raise IngestError("Source has no video stream")
        if audio is None:
            raise IngestError("Source has no audio stream")

        fps_num, fps_den = _frame_rate(video)
        width = _require_int(video.get("width"), "width")
        height = _require_int(video.get("height"), "height")
        sample_rate = _require_int(audio.get("sample_rate"), "sample_rate")
        timebase = Timebase(fps_num, fps_den, sample_rate)

        frames = _frame_count(video, payload, timebase)
        return MediaInfo(
            source_path=str(source.resolve()),
            duration_frames=frames,
            fps_num=fps_num,
            fps_den=fps_den,
            width=width,
            height=height,
            audio_sample_rate=sample_rate,
        )

    def is_vfr(self, path: Path) -> bool:
        """Whether the container reports a variable frame rate."""

        source = Path(path).expanduser()
        payload = self._run_json(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-select_streams",
                "v:0",
                "-show_streams",
                str(source),
            ]
        )
        streams = payload.get("streams") or []
        video = _first_stream(streams, "video", skip_attached_picture=True)
        if video is None:
            return False
        raw = video.get("r_frame_rate")
        average = video.get("avg_frame_rate")
        if not isinstance(raw, str) or not isinstance(average, str):
            return False
        return _rate_value(raw) != _rate_value(average)

    def normalize_cfr(
        self,
        source: Path,
        destination: Path,
        *,
        fps_num: int,
        fps_den: int,
    ) -> Path:
        """Transcode/remux a VFR source to a constant rational frame rate."""

        source_path = Path(source).expanduser()
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.stem}.part{target.suffix}")
        self._run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-vf",
                (
                    f"fps=fps={fps_num}/{fps_den},"
                    "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
                    "format=yuv420p,setparams=color_primaries=bt709:"
                    "color_trc=bt709:colorspace=bt709"
                ),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-color_primaries",
                "bt709",
                "-color_trc",
                "bt709",
                "-colorspace",
                "bt709",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(temporary),
            ]
        )
        temporary.replace(target)
        return target

    def normalize_session_source(
        self,
        source: Path,
        destination: Path,
        *,
        width: int,
        height: int,
        fps_num: int,
        fps_den: int,
        sample_rate: int,
    ) -> Path:
        """Normalize one session clip to a common CFR/resolution/audio format."""

        source_path = Path(source).expanduser()
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.stem}.part{target.suffix}")
        filters = (
            f"fps={fps_num}/{fps_den},"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
        self._run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-vf",
                filters,
                "-af",
                f"aresample={sample_rate}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                str(sample_rate),
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(temporary),
            ]
        )
        temporary.replace(target)
        return target

    def build_proxy(
        self,
        source: Path,
        destination: Path,
        *,
        height: int = 540,
        preset: str = "veryfast",
        crf: int = 23,
        audio: bool = True,
        fps: int | None = None,
        fast: bool = False,
        encoder: str = "auto",
    ) -> Path:
        """Build a preview-only H.264/AAC proxy."""

        source_path = Path(source).expanduser()
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.stem}.part{target.suffix}")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        if fast:
            command.extend(["-skip_frame", "nokey"])
        command.extend(["-i", str(source_path)])
        command.extend(
            [
                "-vf",
                (
                    f"fps={max(1, int(fps))},scale=-2:{max(144, int(height))}"
                    if fps
                    else f"scale=-2:{max(144, int(height))}"
                ),
            ]
        )
        chosen = str(encoder or "auto").lower()
        if chosen == "auto":
            from videoflow.exporters.mp4 import video_encoder

            chosen = video_encoder()
        if fast and chosen in {"libx264", "x264", "cpu"}:
            command.extend(["-c:v", "mpeg4", "-q:v", "8"])
        elif chosen in {"nvenc", "h264_nvenc"}:
            command.extend(
                [
                    "-c:v",
                    "h264_nvenc",
                    "-preset",
                    "p1",
                    "-rc",
                    "vbr",
                    "-cq",
                    str(max(0, min(51, int(crf)))),
                    "-b:v",
                    "0",
                    "-pix_fmt",
                    "yuv420p",
                ]
            )
        else:
            command.extend(
                ["-c:v", "libx264", "-preset", preset, "-crf", str(max(0, min(51, int(crf))))]
            )
        if audio:
            command.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            command.append("-an")
        command.extend(["-movflags", "+faststart", str(temporary)])
        self._run(command)
        temporary.replace(target)
        return target

