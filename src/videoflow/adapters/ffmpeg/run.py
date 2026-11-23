"""Process execution and cancellation helpers."""

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
from videoflow.application.process_control import terminate_process
from videoflow.domain.errors import IngestError, JobCancelledError
from videoflow.domain.state import MediaInfo
from videoflow.domain.timebase import Rounding, Timebase
from videoflow.runtime import find_binary

DEFAULT_TIMEOUT_SECONDS = 600

DEFAULT_RENDER_TIMEOUT_SECONDS = 3600

_SILENCE_START = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")




def _pkg():
    return sys.modules["videoflow.adapters.ffmpeg"]


class RunMixin:
    def _run_json(self, args: list[str]) -> dict[str, Any]:
        raw = self._run(args)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IngestError("ffprobe returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise IngestError("ffprobe returned an unexpected payload")
        return payload

    def _run(self, args: list[str]) -> str:
        stdout, _ = self._capture(args)
        return stdout

    def _terminate(self, process: _pkg().subprocess.Popen[str]) -> None:
        if os.name == "nt":
            terminate_process(process, timeout=0.5)
            return
        try:
            _pkg().os.killpg(_pkg().os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            with contextlib.suppress(OSError):
                process.terminate()
        try:
            process.wait(timeout=0.5)
        except _pkg().subprocess.TimeoutExpired:
            try:
                _pkg().os.killpg(_pkg().os.getpgid(process.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                with contextlib.suppress(OSError):
                    process.kill()
            process.wait(timeout=2.0)

    def _capture(
        self, args: list[str], *, timeout: int = DEFAULT_TIMEOUT_SECONDS
    ) -> tuple[str, str]:
        run_args, script_dir = _filter_script_args(args)
        try:
            binary = _pkg().find_binary(run_args[0])
            if binary is None:
                raise IngestError(
                    f"{run_args[0]} is not available. Place it next to the executable."
                )
            if self.cancel_event is not None and self.cancel_event.is_set():
                raise JobCancelledError("Cancelled")
            self._emit("debug", "$ " + " ".join([Path(binary).name, *run_args[1:]]))
            process = _pkg().subprocess.Popen(
                [binary, *run_args[1:]],
                stdout=_pkg().subprocess.PIPE,
                stderr=_pkg().subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            deadline = _pkg().time.monotonic() + max(1, timeout)
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.15)
                    break
                except _pkg().subprocess.TimeoutExpired:
                    if self.cancel_event is not None and self.cancel_event.is_set():
                        self._terminate(process)
                        raise JobCancelledError("Cancelled") from None
                    if _pkg().time.monotonic() >= deadline:
                        self._terminate(process)
                        raise IngestError(f"{run_args[0]} timed out after {timeout}s") from None
            if process.returncode != 0:
                tail = stderr.strip().splitlines()[-50:]
                command = " ".join([Path(binary).name, *run_args[1:]])
                if tail:
                    summary = " ".join(tail[-3:])
                    message = f"{run_args[0]} failed: {summary}"
                elif process.returncode < 0:
                    signum = -process.returncode
                    try:
                        name = signal.Signals(signum).name
                    except ValueError:
                        name = f"signal {signum}"
                    message = (
                        f"{run_args[0]} was killed by {name}; "
                        "this usually means the render ran out of memory or was "
                        "terminated by the system"
                    )
                else:
                    message = f"{run_args[0]} failed with exit code {process.returncode}"
                self._emit("error", "\n".join(tail) or message)
                raise IngestError(
                    message,
                    command=command,
                    stderr=stderr,
                    returncode=process.returncode,
                )
            return stdout, stderr
        finally:
            if script_dir is not None:
                shutil.rmtree(script_dir, ignore_errors=True)


