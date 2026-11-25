"""Pure helpers used by the FFmpeg adapter mixins."""

# ruff: noqa: F401


import contextlib
import functools
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

from videoflow.application.music import music_filter
from videoflow.domain.errors import IngestError, JobCancelledError, VideoFlowError
from videoflow.domain.state import MediaInfo
from videoflow.domain.timebase import Rounding, Timebase
from videoflow.runtime import find_binary

DEFAULT_TIMEOUT_SECONDS = 600

DEFAULT_RENDER_TIMEOUT_SECONDS = 3600

_SILENCE_START = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")



FILTER_COMPLEX_SCRIPT_FLAG = "-filter_complex_script"

_FALLBACK_FONT_FAMILIES = {
    "arial",
    "segoeui",
    "inter",
    "liberationsans",
    "dejavusans",
    "notosans",
}


def ass_font_names(ass_path: Path | str) -> list[str]:
    """Return the font families referenced by an ASS stylesheet."""

    path = Path(ass_path).expanduser()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    names: list[str] = []
    for line in lines:
        if not line.strip().casefold().startswith("style:"):
            continue
        fields = line.split(",", 2)
        if len(fields) < 2:
            continue
        name = fields[1].strip()
        if name and name not in names:
            names.append(name)
    return names


def _font_key(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def prepare_isolated_fonts_dir(
    project_dir: Path | str,
    font_names: Sequence[str] = (),
) -> Path:
    """Copy only the fonts used by captions into ``work/fonts``.

    Passing a tiny, project-local directory to libass avoids the slow Windows
    ``C:/Windows/Fonts`` cache scan and keeps font lookup deterministic.
    """

    from videoflow.application.fonts import font_family, fonts_dir, list_system_fonts

    destination = Path(project_dir).expanduser() / "work" / "fonts"
    if destination.is_dir():
        shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    wanted = {_font_key(item) for item in font_names if _font_key(item)}
    fallbacks = _FALLBACK_FONT_FAMILIES
    copied: set[str] = set()

    def copy(source: Path) -> None:
        if not source.is_file() or source.suffix.casefold() not in {".ttf", ".otf"}:
            return
        target = destination / source.name
        if target.name in copied:
            return
        try:
            shutil.copy2(source, target)
        except OSError:
            return
        copied.add(target.name)

    user_fonts = [path for path in sorted(fonts_dir().glob("*")) if path.is_file()]
    if not wanted:
        for path in user_fonts:
            copy(path)
        if copied:
            return destination
    for path in user_fonts:
        stem = _font_key(path.stem)
        try:
            family = _font_key(font_family(path.read_bytes()))
        except Exception:  # noqa: BLE001 - fallback to the filename
            family = stem
        if {stem, family} & (wanted | fallbacks):
            copy(path)
    if not copied and wanted:
        for item in list_system_fonts():
            file_path = Path(str(item.get("file") or "")).expanduser()
            family = _font_key(str(item.get("family") or ""))
            stem = _font_key(file_path.stem)
            if {family, stem} & (wanted | fallbacks):
                copy(file_path)
                if len(copied) >= 8:
                    break
    if not copied:
        for item in list_system_fonts():
            file_path = Path(str(item.get("file") or "")).expanduser()
            if {_font_key(file_path.stem), _font_key(str(item.get("family") or ""))} & fallbacks:
                copy(file_path)
                if len(copied) >= 4:
                    break
    if not copied:
        for path in user_fonts:
            copy(path)
    return destination


class FilterScriptUnsupportedError(VideoFlowError):
    """The FFmpeg build accepts neither filter-script spelling."""

    code = "ffmpeg_unsupported_filter_script"


def _supports_filter_script(ffmpeg_bin: str, flag: str) -> bool:
    """Prove one filter-script flag with a tiny real encode."""

    graph = "[0:v]null[out]"
    with tempfile.TemporaryDirectory(prefix="vf-filter-probe-") as raw:
        script = Path(raw) / "graph.txt"
        script.write_text(graph, encoding="utf-8")
        try:
            completed = subprocess.run(
                [
                    ffmpeg_bin,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=16x16:d=0.1",
                    flag,
                    str(script),
                    "-map",
                    "[out]",
                    "-frames:v",
                    "1",
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return False
    return completed.returncode == 0


@functools.lru_cache(maxsize=64)
def probe_filter_script_flag(ffmpeg_bin: str) -> str:
    """Return the filter-script flag supported by this FFmpeg build.

    FFmpeg 7.1/8/9 removed ``-filter_complex_script`` in favour of the generic
    ``-/filter_complex`` file form. FFmpeg 6 and early 7.x still need the old
    spelling. The probe runs a real one-frame encode so a build that only lists
    the option but cannot use it is rejected too.
    """

    binary = str(ffmpeg_bin or "ffmpeg")
    for flag in ("-/filter_complex", FILTER_COMPLEX_SCRIPT_FLAG):
        if _supports_filter_script(binary, flag):
            return flag
    raise FilterScriptUnsupportedError(
        "FFmpeg supports neither '-/filter_complex' nor "
        "'-filter_complex_script'; update the bundled FFmpeg."
    )


def ffmpeg_supports_filter_complex_script(ffmpeg_bin: str) -> bool:
    """Whether this FFmpeg accepts a filter graph from a script file."""

    try:
        probe_filter_script_flag(ffmpeg_bin)
    except FilterScriptUnsupportedError:
        return False
    return True


def build_filter_complex_args(
    graph: str,
    script_path: Path,
    *,
    ffmpeg_bin: str,
    inline_limit: int = 6000,
) -> list[str]:
    """Return safe filter_complex arguments for FFmpeg 6/7/8/9."""

    if len(graph) <= inline_limit:
        return ["-filter_complex", graph]
    target = Path(script_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(graph, encoding="utf-8")
    return [probe_filter_script_flag(ffmpeg_bin), str(target)]


def _filter_script_args(
    args: list[str], *, ffmpeg_bin: str = ""
) -> tuple[list[str], Path | None]:
    """Move a large filter graph to the FFmpeg version's script flag.

    Linux ``ARG_MAX`` is easy to exceed with a thousand-clip graph. Keeping the
    graph in a temporary file also makes FFmpeg error messages readable.
    """

    try:
        index = args.index("-filter_complex")
    except ValueError:
        return args, None
    if index + 1 >= len(args):
        return args, None
    graph = args[index + 1]
    if len(graph) <= 4096:
        return args, None
    directory = Path(tempfile.mkdtemp(prefix="vf-filter-"))
    path = directory / "graph.txt"
    try:
        replacement = build_filter_complex_args(
            graph,
            path,
            ffmpeg_bin=ffmpeg_bin or args[0],
            inline_limit=4096,
        )
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    updated = [*args[:index], *replacement, *args[index + 2 :]]
    return updated, directory


def _cutout_graph(
    base: str,
    width: int,
    height: int,
    *,
    corner_radius: float,
    margin: float,
    head_overlap: float,
    mask_path: Path | None = None,
    mask_index: int = 1,
) -> str:
    """Build a blurred-background presenter window with rounded corners."""

    margin = max(0.0, min(0.3, margin))
    head_overlap = max(0.0, min(0.4, head_overlap))
    fg_w = max(2, int(width * (1 - margin * 2)))
    fg_h = max(2, int(height * 0.72))
    radius = max(0, min(fg_w, fg_h, int(fg_w * max(0.0, min(0.5, corner_radius)))))
    offset = max(0.0, min(1.0, head_overlap)) * 0.15
    if mask_path is not None:
        foreground = (
            f"[fg0]scale={fg_w}:{fg_h}:force_original_aspect_ratio=increase,"
            f"crop={fg_w}:{fg_h},format=rgba[fgraw];"
            f"[{mask_index}:v]format=gray,loop=loop=-1:size=1:start=0[mask];"
            "[fgraw][mask]alphamerge[fg];"
        )
    else:
        alpha = (
            "if(lte(hypot(max(0,abs(X-(W-1)/2)-((W-1)/2-"
            f"{radius})),max(0,abs(Y-(H-1)/2)-((H-1)/2-{radius}))),{radius}),255,0)"
        )
        foreground = (
            f"[fg0]scale={fg_w}:{fg_h}:force_original_aspect_ratio=increase,"
            f"crop={fg_w}:{fg_h},format=rgba,"
            f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{alpha}'[fg];"
        )
    return (
        f"{base},split=2[bg0][fg0];"
        "[bg0]boxblur=24:8,eq=brightness=-0.18[bg];"
        f"{foreground}"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2-(H*{offset:.4f}):shortest=1[vout]"
    )


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def escape_ffmpeg_filter_path(path: Path | str) -> str:
    """Return a path safe inside ``ass=``, ``subtitles=`` and ``drawtext=``.

    Backslashes are normalized to ``/`` and the Windows drive colon becomes
    ``C\\:/...``. Apostrophes are escaped for FFmpeg's filter parser. A Windows
    path is kept as-is instead of being resolved against the current directory
    of a non-Windows host, which keeps the helper testable from Linux.
    """

    raw = str(path)
    if _WINDOWS_DRIVE.match(raw):
        value = raw.replace("\\", "/")
    else:
        value = str(Path(raw).expanduser().resolve()).replace("\\", "/")
    return value.replace(":", "\\:").replace("'", "\\'")


def _filter_path(path: Path) -> str:
    return escape_ffmpeg_filter_path(path)


def parse_silence(
    stderr: str,
    duration_samples: int,
    sample_rate: int,
) -> list[tuple[int, int]]:
    """Parse ``silencedetect`` output into non-overlapping sample spans."""

    starts = [float(item) for item in _SILENCE_START.findall(stderr)]
    ends = [float(item) for item in _SILENCE_END.findall(stderr)]
    pairs: list[tuple[int, int]] = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else duration_samples / sample_rate
        start_sample = _seconds_to_samples(start, sample_rate)
        end_sample = min(duration_samples, _seconds_to_samples(end, sample_rate))
        if end_sample > start_sample:
            pairs.append((max(0, start_sample), end_sample))
    pairs.sort()
    merged: list[tuple[int, int]] = []
    for start, end in pairs:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _complement(silence: list[tuple[int, int]], duration_samples: int) -> list[tuple[int, int]]:
    speech: list[tuple[int, int]] = []
    cursor = 0
    for start, end in silence:
        if start > cursor:
            speech.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration_samples:
        speech.append((cursor, duration_samples))
    return speech


def _seconds_to_samples(seconds: float, sample_rate: int) -> int:
    value = Fraction(str(seconds)) * sample_rate
    return (value.numerator + value.denominator // 2) // value.denominator


def _first_stream(
    streams: list[dict[str, Any]],
    codec_type: str,
    *,
    skip_attached_picture: bool = False,
) -> dict[str, Any] | None:
    for stream in streams:
        if stream.get("codec_type") != codec_type:
            continue
        if skip_attached_picture and stream.get("disposition", {}).get("attached_pic") == 1:
            continue
        return stream
    return None


def _rate_value(raw: str) -> float:
    if "/" in raw:
        numerator, denominator = raw.split("/", 1)
        try:
            return float(numerator) / max(1e-9, float(denominator))
        except ValueError:
            return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _frame_rate(video: dict[str, Any]) -> tuple[int, int]:
    for key in ("r_frame_rate", "avg_frame_rate"):
        raw = video.get(key)
        if not isinstance(raw, str) or "/" not in raw:
            continue
        numerator, denominator = raw.split("/", 1)
        try:
            fps_num = int(numerator)
            fps_den = int(denominator)
        except ValueError:
            continue
        if fps_num > 0 and fps_den > 0:
            return fps_num, fps_den
    raise IngestError("FFprobe did not report a usable frame rate")


def _frame_count(video: dict[str, Any], payload: dict[str, Any], timebase: Timebase) -> int:
    raw_frames = video.get("nb_frames")
    if isinstance(raw_frames, str) and raw_frames.isdigit() and int(raw_frames) > 0:
        return int(raw_frames)
    duration = video.get("duration")
    if not isinstance(duration, str) or duration in {"N/A", ""}:
        duration = (payload.get("format") or {}).get("duration")
    if not isinstance(duration, str) or duration in {"N/A", ""}:
        raise IngestError("FFprobe did not report a duration")
    try:
        seconds = Fraction(duration)
    except ValueError as exc:
        raise IngestError(f"FFprobe returned an invalid duration: {duration}") from exc
    return timebase.seconds_to_frames(seconds, Rounding.NEAREST)


def _require_int(value: object, label: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise IngestError(f"FFprobe did not report {label}") from exc
    if parsed <= 0:
        raise IngestError(f"FFprobe reported an invalid {label}")
    return parsed


def _piece_focus(
    keyframes: Sequence[tuple[float, float]] | None,
    start_sample: int,
    end_sample: int,
    sample_rate: int,
    default: float,
) -> float:
    if not keyframes or sample_rate <= 0:
        return default
    start = start_sample / sample_rate
    end = end_sample / sample_rate
    values = [focus for time_sec, focus in keyframes if start <= time_sec <= end]
    if not values:
        nearest = min(keyframes, key=lambda item: abs(item[0] - start))
        values = [nearest[1]]
    return sum(values) / len(values)


def _piece_keyframes(
    keyframes: Sequence[tuple[float, float]] | None,
    start_sample: int,
    end_sample: int,
    sample_rate: int,
    *,
    max_points: int = 12,
) -> list[tuple[float, float]]:
    """Return normalized keyframes for one rendered piece."""

    if not keyframes or sample_rate <= 0 or end_sample <= start_sample:
        return []
    start = start_sample / sample_rate
    end = end_sample / sample_rate
    duration = end - start
    selected = [
        (max(0.0, min(duration, time_sec - start)), focus)
        for time_sec, focus in keyframes
        if start <= time_sec <= end
    ]
    if not selected:
        nearest = min(keyframes, key=lambda item: abs(item[0] - start))
        selected = [(0.0, nearest[1]), (duration, nearest[1])]
    if selected[0][0] > 0:
        selected.insert(0, (0.0, selected[0][1]))
    if selected[-1][0] < duration:
        selected.append((duration, selected[-1][1]))
    selected = [
        (round(time_sec, 3), round(max(0.05, min(0.95, focus)), 4))
        for time_sec, focus in selected
    ]
    if selected and max(focus for _time, focus in selected) - min(
        focus for _time, focus in selected
    ) < 0.01:
        return [(0.0, selected[0][1])]
    if len(selected) <= max_points:
        return selected
    step = (len(selected) - 1) / (max_points - 1)
    indexes = sorted({round(index * step) for index in range(max_points)})
    return [selected[index] for index in indexes]


def _crop_expression(keyframes: Sequence[tuple[float, float]]) -> str:
    """Build a piecewise-linear FFmpeg crop expression for x focus."""

    points = list(keyframes)
    if len(points) < 2:
        return str(points[0][1] if points else 0.5)
    expression = str(points[-1][1])
    for index in range(len(points) - 2, -1, -1):
        t0, v0 = points[index]
        t1, v1 = points[index + 1]
        span = max(0.001, t1 - t0)
        segment = f"lerp({v0},{v1},(t-{t0})/{span})"
        expression = f"if(lt(t,{t1}),{segment},{expression})"
    return expression
