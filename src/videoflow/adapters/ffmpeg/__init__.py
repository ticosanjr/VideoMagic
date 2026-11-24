"""FFmpeg/FFprobe adapter composed from domain mixins."""


# ruff: noqa: F401
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

from videoflow.adapters.ffmpeg.audio import AudioMixin
from videoflow.adapters.ffmpeg.base import BaseMixin
from videoflow.adapters.ffmpeg.frames import FramesMixin
from videoflow.adapters.ffmpeg.helpers import (
    FILTER_COMPLEX_SCRIPT_FLAG,
    FilterScriptUnsupportedError,
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
    build_filter_complex_args,
    parse_silence,
    probe_filter_script_flag,
)
from videoflow.adapters.ffmpeg.probe import ProbeMixin
from videoflow.adapters.ffmpeg.render import RenderMixin
from videoflow.adapters.ffmpeg.run import RunMixin
from videoflow.adapters.ffmpeg.shorts import ShortsMixin
from videoflow.runtime import find_binary


class FFmpegAdapter(
    BaseMixin,
    ProbeMixin,
    AudioMixin,
    FramesMixin,
    ShortsMixin,
    RenderMixin,
    RunMixin,
):
    """Concrete adapter preserving the historical public API."""


__all__ = [
    "FFmpegAdapter",
    "FILTER_COMPLEX_SCRIPT_FLAG",
    "FilterScriptUnsupportedError",
    "_complement",
    "_crop_expression",
    "_cutout_graph",
    "_filter_path",
    "_filter_script_args",
    "_first_stream",
    "build_filter_complex_args",
    "probe_filter_script_flag",
    "_frame_count",
    "_frame_rate",
    "_piece_focus",
    "_piece_keyframes",
    "_rate_value",
    "_require_int",
    "_seconds_to_samples",
    "parse_silence",
]
