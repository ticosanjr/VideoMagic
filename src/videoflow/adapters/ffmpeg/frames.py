"""Preview and keyframe extraction."""

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




class FramesMixin:
    def transcode_preview(
        self,
        source: Path,
        destination: Path,
        *,
        width: int = 540,
    ) -> Path:
        """Write a small H.264/AAC proxy for in-browser preview."""

        source_path = Path(source).expanduser()
        target = Path(destination).expanduser()
        if not source_path.is_file():
            raise IngestError(f"Preview source does not exist: {source_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._capture(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-vf",
                f"scale={max(2, width)}:-2",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "28",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-movflags",
                "+faststart",
                str(target),
            ]
        )
        return target

    def extract_frames(
        self,
        source: Path,
        directory: Path,
        *,
        fps: float = 1.0,
        width: int = 640,
        max_frames: int | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> list[Path]:
        """Extract JPEG samples for vision analysis and return them in order."""

        source_path = Path(source).expanduser()
        target_dir = Path(directory).expanduser()
        target_dir.mkdir(parents=True, exist_ok=True)
        for existing in target_dir.glob("frame-*.jpg"):
            with contextlib.suppress(OSError):
                existing.unlink()
        rate = max(0.05, min(60.0, float(fps)))
        self._capture(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-vf",
                f"fps={rate:.6f},scale={max(64, int(width))}:-2",
                "-q:v",
                "3",
                *(["-frames:v", str(max(1, int(max_frames)))] if max_frames is not None else []),
                str(target_dir / "frame-%06d.jpg"),
            ],
            timeout=timeout,
        )
        return sorted(target_dir.glob("frame-*.jpg"))

    def extract_keyframe(
        self,
        source: Path,
        destination: Path,
        *,
        time_sec: float,
        max_size: int = 544,
        quality: int = 78,
    ) -> Path:
        """Extract one JPEG keyframe bounded by ``max_size`` on its long edge."""

        if time_sec < 0:
            raise IngestError("Keyframe time must be non-negative")
        source_path = Path(source).expanduser()
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        limit = max(64, int(max_size))
        qscale = max(2, min(31, round(31 - (max(1, min(100, quality)) * 0.29))))
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{time_sec:.6f}",
            "-i",
            str(source_path),
            "-frames:v",
            "1",
            "-vf",
            (
                f"scale='if(gt(iw,ih),{limit},-2)':"
                f"'if(gt(iw,ih),-2,{limit})':flags=lanczos"
            ),
            "-q:v",
            str(qscale),
            str(target),
        ]
        self._capture(command)
        return target

    def render_thumbnail(
        self,
        source: Path,
        destination: Path,
        *,
        time_sec: float,
        ass_path: Path | None = None,
        fontsdir: str | None = None,
        height: int | None = None,
    ) -> Path:
        """Extract one frame, optionally burn the ASS title and scale to height."""

        if time_sec < 0:
            raise IngestError("Thumbnail time must be non-negative")
        source_path = Path(source).expanduser()
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{time_sec:.6f}",
            "-i",
            str(source_path),
        ]
        filters: list[str] = []
        if ass_path is not None:
            ass_filter = f"ass='{_filter_path(ass_path)}'"
            if fontsdir:
                ass_filter += f":fontsdir='{_filter_path(Path(fontsdir))}'"
            filters.append(ass_filter)
        if height is not None:
            filters.append(f"scale=-2:{max(64, min(2160, int(height)))}")
        if filters:
            command.extend(["-vf", ",".join(filters)])
        command.extend(["-frames:v", "1", str(target)])
        self._capture(command)
        return target

