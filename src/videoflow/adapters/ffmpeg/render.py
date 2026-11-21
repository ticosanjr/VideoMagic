"""Longform render entrypoint."""

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
import sys
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


def _pkg():
    return sys.modules["videoflow.adapters.ffmpeg"]

DEFAULT_TIMEOUT_SECONDS = 600

DEFAULT_RENDER_TIMEOUT_SECONDS = 3600

_SILENCE_START = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")




class RenderMixin:
    def render(
        self,
        args: list[str],
        *,
        timeout: int = DEFAULT_RENDER_TIMEOUT_SECONDS,
        progress: Callable[[int], None] | None = None,
    ) -> None:
        """Run FFmpeg, optionally streaming ``-progress`` frame counts."""

        if progress is None:
            self._capture(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                timeout=timeout,
            )
            return
        binary = _pkg().find_binary("ffmpeg")
        if binary is None:
            raise IngestError("ffmpeg is not available. Place it next to the executable.")
        command = [
            binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *args,
            "-progress",
            "pipe:1",
            "-nostats",
        ]
        process = _pkg().subprocess.Popen(
            command,
            stdout=_pkg().subprocess.PIPE,
            stderr=_pkg().subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        lines: queue.Queue[str] = queue.Queue()

        def reader() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line)

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()
        tail: list[str] = []
        deadline = _pkg().time.monotonic() + max(1, timeout)
        while process.poll() is None:
            if self.cancel_event is not None and self.cancel_event.is_set():
                self._terminate(process)
                raise JobCancelledError("Cancelled") from None
            if _pkg().time.monotonic() >= deadline:
                self._terminate(process)
                raise IngestError(f"render timed out after {timeout}s") from None
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            tail.append(line.rstrip())
            tail = tail[-100:]
            if line.startswith("frame="):
                with contextlib.suppress(ValueError):
                    progress(int(line.split("=", 1)[1].strip()))
        reader_thread.join(timeout=1.0)
        while not lines.empty():
            tail.append(lines.get_nowait().rstrip())
        tail = tail[-100:]
        if process.returncode != 0:
            self._emit("error", "\n".join(tail[-50:]) or "ffmpeg failed")
            summary = " ".join(tail[-3:])
            raise IngestError(
                f"ffmpeg failed: {summary or 'unknown error'}",
                command=" ".join(command),
                stderr="\n".join(tail),
            )

