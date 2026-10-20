"""FFmpeg/FFprobe adapter.

Only two operations are needed for the deterministic core: probe the source and
extract the analysis WAV. Rendering lands with the shorts pass.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import uuid4

from videoflow.domain.errors import IngestError
from videoflow.domain.state import MediaInfo
from videoflow.domain.timebase import Rounding, Timebase
from videoflow.runtime import find_binary

DEFAULT_TIMEOUT_SECONDS = 600

_SILENCE_START = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")


class FFmpegAdapter:
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

    def render_short(
        self,
        source: Path,
        pieces: list[tuple[int, int]] | tuple[tuple[int, int], ...],
        destination: Path,
        *,
        sample_rate: int,
        ass_path: Path | None = None,
        width: int = 1080,
        height: int = 1920,
    ) -> Path:
        """Render concatenated source pieces as a vertical H.264 short."""

        if not pieces:
            raise IngestError("No pieces to render")
        source_path = Path(source).expanduser()
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        work = target.parent / f".{target.stem}.{uuid4().hex}.work"
        work.mkdir()
        try:
            rendered: list[Path] = []
            for index, (start, end) in enumerate(pieces):
                piece = work / f"piece-{index:02d}.mp4"
                duration = (end - start) / sample_rate
                self._capture(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-ss",
                        f"{start / sample_rate:.6f}",
                        "-t",
                        f"{duration:.6f}",
                        "-i",
                        str(source_path),
                        "-vf",
                        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                        f"crop={width}:{height},setsar=1",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "20",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "libmp3lame",
                        "-b:a",
                        "192k",
                        str(piece),
                    ]
                )
                rendered.append(piece)
            if len(rendered) == 1:
                combined = rendered[0]
            else:
                list_file = work / "concat.txt"
                list_file.write_text(
                    "\n".join(
                        f"file '{str(item.resolve()).replace(chr(92), '/')}'"
                        for item in rendered
                    )
                    + "\n",
                    encoding="utf-8",
                )
                combined = work / "combined.mp4"
                self._capture(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(list_file),
                        "-c",
                        "copy",
                        str(combined),
                    ]
                )
            final = combined
            if ass_path is not None:
                final = work / "final.mp4"
                self._capture(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(combined),
                        "-vf",
                        f"ass='{_filter_path(ass_path)}'",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "20",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "copy",
                        "-movflags",
                        "+faststart",
                        str(final),
                    ]
                )
            shutil.move(str(final), target)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return target

    def render(self, args: list[str]) -> None:
        raise NotImplementedError("FFmpeg render is not implemented in this scaffold")

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

    def _capture(self, args: list[str]) -> tuple[str, str]:
        binary = find_binary(args[0])
        if binary is None:
            raise IngestError(f"{args[0]} is not available. Place it next to the executable.")
        try:
            completed = subprocess.run(
                [binary, *args[1:]],
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise IngestError(f"{args[0]} timed out after {DEFAULT_TIMEOUT_SECONDS}s") from exc
        if completed.returncode != 0:
            stderr = " ".join(completed.stderr.strip().splitlines()[-3:])
            raise IngestError(f"{args[0]} failed: {stderr or 'unknown error'}")
        return completed.stdout, completed.stderr


def _filter_path(path: Path) -> str:
    value = str(Path(path).expanduser().resolve()).replace("\\", "/")
    return value.replace(":", "\\:").replace("'", "\\'")


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
