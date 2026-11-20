"""FFmpeg/FFprobe adapter.

Only two operations are needed for the deterministic core: probe the source and
extract the analysis WAV. Rendering lands with the shorts pass.
"""

from __future__ import annotations

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

from videoflow.application.music import music_filter
from videoflow.domain.errors import IngestError, JobCancelledError
from videoflow.domain.state import MediaInfo
from videoflow.domain.timebase import Rounding, Timebase
from videoflow.runtime import find_binary

DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_RENDER_TIMEOUT_SECONDS = 3600

_SILENCE_START = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")


class FFmpegAdapter:
    def __init__(
        self,
        log: Callable[[str, str], None] | None = None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self._log = log
        self.cancel_event = cancel_event

    def _emit(self, level: str, message: str) -> None:
        if self._log is not None:
            self._log(level, message)

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
    ) -> Path:
        """Build a preview-only H.264/AAC proxy."""

        source_path = Path(source).expanduser()
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.stem}.part{target.suffix}")
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-vf",
            f"scale=-2:{max(144, int(height))}",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(max(0, min(51, int(crf)))),
        ]
        if audio:
            command.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            command.append("-an")
        command.extend(["-movflags", "+faststart", str(temporary)])
        self._run(command)
        temporary.replace(target)
        return target

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
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            "2",
            "-ar",
            str(sample_rate),
        ]
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
        fontsdir: str | None = None,
        audio_filters: Sequence[str] | None = None,
        overlay_path: Path | None = None,
        overlay_position: str = "bottom_right",
        overlay_margin: int = 32,
        overlay_width_ratio: float = 0.18,
        overlay_opacity: float = 0.9,
        music_path: Path | None = None,
        music_volume: float = 0.18,
        music_ducking: bool = True,
        music_fade_in_ms: int = 250,
        music_fade_out_ms: int = 500,
        intro_path: Path | None = None,
        outro_path: Path | None = None,
        intro_duration_sec: float = 2.0,
        outro_duration_sec: float = 2.0,
        crop_focus_x: float = 0.5,
        crop_focus_y: float = 0.5,
        crop_keyframes: Sequence[tuple[float, float]] | None = None,
        split_screen: bool = False,
        split_screen_zoom: float = 1.0,
        split_screen_focus_left: float = 0.5,
        split_screen_focus_right: float = 0.5,
        second_source_path: Path | None = None,
        mix_second_audio: bool = False,
        broll_path: Path | None = None,
        broll_start_sec: float = 0.0,
        broll_duration_sec: float = 2.0,
        broll_clips: Sequence[tuple[Path, float, float]] | None = None,
        sfx_clips: Sequence[tuple[Path, float, float]] | None = None,
        cutout: bool = False,
        cutout_corner_radius: float = 0.08,
        cutout_margin: float = 0.04,
        cutout_head_overlap: float = 0.12,
        crossfade_ms: int = 15,
        layout_mode: str = "",
        punch_in_scale: float = 1.06,
        visual_path: Path | None = None,
        headline_text: str = "",
        fps: int = 30,
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
                second = Path(second_source_path).expanduser() if second_source_path else None
                visual = Path(visual_path).expanduser() if visual_path else None
                mask_input: list[str] = []
                if split_screen:
                    half = max(2, width // 2)
                    zoom = max(1.0, min(2.0, float(split_screen_zoom)))
                    focus_left = max(0.0, min(1.0, float(split_screen_focus_left)))
                    focus_right = max(0.0, min(1.0, float(split_screen_focus_right)))
                    if second is not None:
                        if not second.is_file():
                            raise IngestError(
                                f"Second split-screen source does not exist: {second}"
                            )
                        audio_graph = (
                            ";[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
                            if mix_second_audio
                            else ""
                        )
                        video_args = [
                            "-filter_complex",
                            (
                                f"[0:v]crop=trunc(iw/(2*{zoom})/2)*2:ih:"
                                f"(iw-ow)*{focus_left}:0,scale={half}:{height}:"
                                "force_original_aspect_ratio=increase,"
                                f"crop={half}:{height},setsar=1[left];"
                                f"[1:v]crop=trunc(iw/(2*{zoom})/2)*2:ih:"
                                f"iw/2+(iw/2-ow)*{focus_right}:0,scale={half}:{height}:"
                                "force_original_aspect_ratio=increase,"
                                f"crop={half}:{height},setsar=1[right];"
                                "[left][right]hstack=inputs=2[v]" + audio_graph
                            ),
                            "-map",
                            "[v]",
                            "-map",
                            "[a]" if mix_second_audio else "0:a?",
                        ]
                    else:
                        video_args = [
                            "-filter_complex",
                            (
                                "[0:v]split=2[a][b];"
                                f"[a]crop=trunc(iw/(2*{zoom})/2)*2:ih:"
                                f"(iw-ow)*{focus_left}:0,scale={half}:{height}:"
                                "force_original_aspect_ratio=increase,"
                                f"crop={half}:{height},setsar=1[left];"
                                f"[b]crop=trunc(iw/(2*{zoom})/2)*2:ih:"
                                f"iw/2+(iw/2-ow)*{focus_right}:0,scale={half}:{height}:"
                                "force_original_aspect_ratio=increase,"
                                f"crop={half}:{height},setsar=1[right];"
                                "[left][right]hstack=inputs=2"
                            ),
                        ]
                elif layout_mode == "split_top_visual" and visual is not None:
                    if not visual.is_file():
                        raise IngestError(f"Top visual does not exist: {visual}")
                    half_height = max(2, height // 2)
                    video_args = [
                        "-filter_complex",
                        (
                            f"[0:v]scale={width}:{half_height}:"
                            "force_original_aspect_ratio=increase,"
                            f"crop={width}:{half_height},setsar=1[presenter];"
                            f"[1:v]scale={width}:{half_height}:"
                            "force_original_aspect_ratio=increase,"
                            f"crop={width}:{half_height},setsar=1[visual];"
                            "[visual][presenter]vstack=inputs=2[v]"
                        ),
                        "-map",
                        "[v]",
                        "-map",
                        "0:a?",
                    ]
                else:
                    piece_keyframes = _piece_keyframes(
                        crop_keyframes,
                        start,
                        end,
                        sample_rate,
                    )
                    from videoflow.application.crop import crop_filter

                    if len(piece_keyframes) > 1:
                        expression = _crop_expression(piece_keyframes)
                        # The expression contains commas from if()/lerp(); quote the
                        # whole x value so FFmpeg does not split it into filters.
                        crop_x = f"'round(({expression})*(iw-ow))'"
                        crop_y = f"round((ih-oh)*{max(0.0, min(1.0, crop_focus_y)):.6f})"
                        crop = f"crop={width}:{height}:{crop_x}:{crop_y}"
                    else:
                        focus = piece_keyframes[0][1] if piece_keyframes else crop_focus_x
                        crop = crop_filter(width, height, fx=focus, fy=crop_focus_y)
                    base = (
                        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                        f"{crop},setsar=1"
                    )
                    if layout_mode == "fullscreen_punchin":
                        scale = max(1.01, min(1.10, float(punch_in_scale)))
                        base += (
                            f",zoompan=z='min(1+0.0006*on,{scale:.4f})':"
                            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                            f"d=1:s={width}x{height}:fps={max(1, int(fps))}"
                        )
                    mask_input: list[str] = []
                    if cutout:
                        from videoflow.application.masks import ensure_rounded_mask

                        margin = max(0.0, min(0.3, cutout_margin))
                        fg_w = max(2, int(width * (1 - margin * 2)))
                        fg_h = max(2, int(height * 0.72))
                        radius = max(
                            0,
                            min(fg_w, fg_h, int(fg_w * max(0.0, min(0.5, cutout_corner_radius)))),
                        )
                        mask_path = ensure_rounded_mask(fg_w, fg_h, radius)
                        graph = _cutout_graph(
                            base,
                            width,
                            height,
                            corner_radius=cutout_corner_radius,
                            margin=cutout_margin,
                            head_overlap=cutout_head_overlap,
                            mask_path=mask_path,
                            mask_index=1,
                        )
                        if mask_path is not None:
                            mask_input = ["-loop", "1", "-i", str(mask_path)]
                        video_args = [
                            "-filter_complex",
                            graph,
                            "-map",
                            "[vout]",
                            "-map",
                            "0:a?",
                        ]
                    else:
                        mask_input = []
                        video_args = ["-vf", base]
                visual_input: list[str] = []
                if (
                    layout_mode == "split_top_visual"
                    and visual is not None
                    and not split_screen
                ):
                    if visual.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"}:
                        visual_input = [
                            "-loop",
                            "1",
                            "-t",
                            f"{duration:.6f}",
                            "-i",
                            str(visual),
                        ]
                    else:
                        visual_input = [
                            "-stream_loop",
                            "-1",
                            "-t",
                            f"{duration:.6f}",
                            "-i",
                            str(visual),
                        ]
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
                        *(
                            [
                                "-ss",
                                f"{start / sample_rate:.6f}",
                                "-t",
                                f"{duration:.6f}",
                                "-i",
                                str(second),
                            ]
                            if split_screen and second is not None
                            else []
                        ),
                        *visual_input,
                        *mask_input,
                        *video_args,
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
                        "-r",
                        str(max(1, int(fps))),
                        *(["-af", ",".join(audio_filters)] if audio_filters else []),
                        str(piece),
                    ]
                )
                rendered.append(piece)
            if len(rendered) == 1:
                combined = rendered[0]
            else:
                crossfade = max(0.0, min(0.1, float(crossfade_ms) / 1000.0))
                durations = [
                    max(0.0, (end - start) / sample_rate) for start, end in pieces
                ]
                if crossfade <= 0:
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
                else:
                    inputs: list[str] = []
                    chains: list[str] = []
                    for index, item in enumerate(rendered):
                        inputs.extend(["-i", str(item)])
                        trim = durations[index] if index < len(durations) else 0.0
                        chains.append(
                            f"[{index}:v]trim=duration={trim:.6f},"
                            f"setpts=PTS-STARTPTS,format=yuv420p[v{index}]"
                        )
                        chains.append(
                            f"[{index}:a]atrim=duration={trim:.6f},"
                            f"asetpts=PTS-STARTPTS[a{index}]"
                        )
                    video_label = "[v0]"
                    audio_label = "[a0]"
                    current = durations[0]
                    for index in range(1, len(rendered)):
                        offset = max(
                            0.0,
                            current - max(crossfade, 1.0 / max(1, int(fps)) + 0.001),
                        )
                        chains.append(
                            f"{video_label}[v{index}]xfade=transition=fade:"
                            f"duration={crossfade:.3f}:offset={offset:.6f}[vx{index}]"
                        )
                        chains.append(
                            f"{audio_label}[a{index}]acrossfade=d={crossfade:.3f}[ax{index}]"
                        )
                        video_label = f"[vx{index}]"
                        audio_label = f"[ax{index}]"
                        current += durations[index] - crossfade
                    combined = work / "combined.mp4"
                    self._capture(
                        [
                            "ffmpeg",
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-y",
                            *inputs,
                            "-filter_complex",
                            ";".join(chains),
                            "-map",
                            video_label,
                            "-map",
                            audio_label,
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
                            str(combined),
                        ]
                    )
            final = combined
            clips: list[tuple[Path, float, float]] = []
            if broll_clips:
                clips = [
                    (Path(path).expanduser(), float(start), float(duration))
                    for path, start, duration in broll_clips
                ]
            elif broll_path is not None:
                clips = [
                    (
                        Path(broll_path).expanduser(),
                        float(broll_start_sec),
                        float(broll_duration_sec),
                    )
                ]
            if clips:
                for path, _, _ in clips:
                    if not path.is_file():
                        raise IngestError(f"B-roll asset does not exist: {path}")
                with_broll = work / "broll.mp4"
                command = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(combined),
                ]
                for path, _, _ in clips:
                    command.extend(["-stream_loop", "-1", "-i", str(path)])
                chains = [
                    (
                        f"[{index + 1}:v]scale={width}:{height}:"
                        "force_original_aspect_ratio=increase,"
                        f"crop={width}:{height},setsar=1[b{index}]"
                    )
                    for index in range(len(clips))
                ]
                current = "[0:v]"
                for index, (_, start, duration) in enumerate(clips):
                    begin = max(0.0, start)
                    finish = begin + max(0.1, duration)
                    label = f"[v{index}]"
                    chains.append(
                        f"{current}[b{index}]overlay=0:0:"
                        f"enable='between(t,{begin:.6f},{finish:.6f})'"
                        f"{label}"
                    )
                    current = label
                command.extend(
                    [
                        "-filter_complex",
                        ";".join(chains),
                        "-map",
                        current,
                        "-map",
                        "0:a?",
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
                        "-t",
                        f"{sum(end - start for start, end in pieces) / sample_rate:.6f}",
                        "-movflags",
                        "+faststart",
                        str(with_broll),
                    ]
                )
                self._capture(command)
                final = with_broll
                combined = with_broll
            if sfx_clips:
                cues = []
                for path, start, volume in sfx_clips:
                    cue = Path(path).expanduser()
                    if cue.is_file():
                        cues.append((cue, max(0.0, float(start)), max(0.0, float(volume))))
                if cues:
                    with_sfx = work / "sfx.mp4"
                    command = [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(combined),
                    ]
                    for cue, _, _ in cues:
                        command.extend(["-i", str(cue)])
                    chains = []
                    labels = ["[0:a]"]
                    for index, (_, start, volume) in enumerate(cues, start=1):
                        delay = round(start * 1000)
                        chains.append(
                            f"[{index}:a]volume={volume:.3f},adelay={delay}|{delay}[s{index}]"
                        )
                        labels.append(f"[s{index}]")
                    chains.append(
                        f"{''.join(labels)}amix=inputs={len(labels)}:"
                        "duration=first:dropout_transition=0[a]"
                    )
                    command.extend(
                        [
                            "-filter_complex",
                            ";".join(chains),
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
                            f"{sum(end - start for start, end in pieces) / sample_rate:.6f}",
                            "-movflags",
                            "+faststart",
                            str(with_sfx),
                        ]
                    )
                    self._capture(command)
                    combined = with_sfx
                    final = with_sfx
            headline_path: Path | None = None
            if headline_text.strip():
                from videoflow.application.captions import build_ass
                from videoflow.domain.config import CaptionStyle

                caption_duration = sum(
                    end - start for start, end in pieces
                ) / sample_rate
                headline_style = CaptionStyle(
                    font_size=max(36, round(height * 0.065)),
                    uppercase=True,
                    alignment=8,
                    position_y=0.18,
                    outline_width=6,
                    effect="static",
                )
                headline_path = work / "headline.ass"
                headline_path.write_text(
                    build_ass(
                        [(0.0, max(0.1, caption_duration), headline_text.strip())],
                        style=headline_style,
                        width=width,
                        height=height,
                    ),
                    encoding="utf-8",
                )
            if ass_path is not None or headline_path is not None:
                from videoflow.application.captions import (
                    merge_ass_files,
                    shift_ass_file,
                )

                final = work / "final.mp4"
                sources = [
                    Path(path)
                    for path in (ass_path, headline_path)
                    if path is not None and Path(path).is_file()
                ]
                burn_path = merge_ass_files(
                    sources,
                    work / "captions-merged.ass",
                )
                if intro_path is not None and intro_duration_sec > 0 and burn_path.is_file():
                    burn_path = shift_ass_file(
                        burn_path,
                        max(0.0, float(intro_duration_sec)),
                        work / "captions-with-intro.ass",
                    )
                ass_filter = f"ass='{_filter_path(burn_path)}'"
                if fontsdir:
                    ass_filter += f":fontsdir='{_filter_path(Path(fontsdir))}'"
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
                        ass_filter,
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
                        "-r",
                        str(max(1, int(fps))),
                        "-fps_mode",
                        "cfr",
                        "-movflags",
                        "+faststart",
                        str(final),
                    ]
                )
            if overlay_path is not None:
                overlay = Path(overlay_path).expanduser()
                if not overlay.is_file():
                    raise IngestError(f"Overlay image does not exist: {overlay}")
                overlay_final = work / "overlay.mp4"
                margin = max(0, int(overlay_margin))
                positions = {
                    "top_left": f"{margin}:{margin}",
                    "top_right": f"W-w-{margin}:{margin}",
                    "bottom_left": f"{margin}:H-h-{margin}",
                    "bottom_right": f"W-w-{margin}:H-h-{margin}",
                    "center": "(W-w)/2:(H-h)/2",
                }
                position = positions.get(overlay_position, positions["bottom_right"])
                logo_width = max(1, int(width * max(0.03, min(1.0, overlay_width_ratio))))
                opacity = max(0.0, min(1.0, overlay_opacity))
                filter_complex = (
                    f"[1:v]format=rgba,scale={logo_width}:-1,"
                    f"colorchannelmixer=aa={opacity}[logo];"
                    f"[0:v][logo]overlay={position}:format=auto[v]"
                )
                overlay_input = (
                    ["-c:v", "libvpx-vp9", "-stream_loop", "-1", "-i", str(overlay)]
                    if overlay.suffix.casefold() == ".webm"
                    else ["-loop", "1", "-i", str(overlay)]
                )
                self._capture(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(final),
                        *overlay_input,
                        "-filter_complex",
                        filter_complex,
                        "-map",
                        "[v]",
                        "-map",
                        "0:a?",
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
                        "-t",
                        f"{sum(end - start for start, end in pieces) / sample_rate:.6f}",
                        "-movflags",
                        "+faststart",
                        str(overlay_final),
                    ]
                )
                final = overlay_final
            if music_path is not None:
                music = Path(music_path).expanduser()
                if not music.is_file():
                    raise IngestError(f"Music file does not exist: {music}")
                music_final = work / "music.mp4"
                duration_sec = sum(end - start for start, end in pieces) / sample_rate
                self._capture(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(final),
                        "-stream_loop",
                        "-1",
                        "-i",
                        str(music),
                        "-filter_complex",
                        music_filter(
                            duration_sec,
                            volume=music_volume,
                            ducking=music_ducking,
                            fade_in_ms=music_fade_in_ms,
                            fade_out_ms=music_fade_out_ms,
                        ),
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
                        f"{duration_sec:.6f}",
                        "-movflags",
                        "+faststart",
                        str(music_final),
                    ]
                )
                final = music_final
            if intro_path is not None or outro_path is not None:
                final = self._attach_cards(
                    final,
                    width=width,
                    height=height,
                    intro_path=intro_path,
                    outro_path=outro_path,
                    intro_duration=intro_duration_sec,
                    outro_duration=outro_duration_sec,
                    work=work,
                    fps=fps,
                )
            loudness_final = work / "loudness.mp4"
            clip_duration = sum(end - start for start, end in pieces) / sample_rate
            if intro_path is not None and intro_duration_sec > 0:
                clip_duration += max(0.2, float(intro_duration_sec))
            if outro_path is not None and outro_duration_sec > 0:
                clip_duration += max(0.2, float(outro_duration_sec))
            self._capture(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(final),
                    "-c:v",
                    "copy",
                    "-af",
                    (
                        "loudnorm=I=-15.5:TP=-1.5:LRA=9,"
                        f"apad=whole_dur={clip_duration:.6f},"
                        f"atrim=0:{clip_duration:.6f}"
                    ),
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-t",
                    f"{clip_duration:.6f}",
                    "-r",
                    str(max(1, int(fps))),
                    "-fps_mode",
                    "cfr",
                    "-movflags",
                    "+faststart",
                    str(loudness_final),
                ]
            )
            final = loudness_final
            shutil.move(str(final), target)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return target

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
        binary = find_binary("ffmpeg")
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
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
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
        deadline = time.monotonic() + max(1, timeout)
        while process.poll() is None:
            if self.cancel_event is not None and self.cancel_event.is_set():
                self._terminate(process)
                raise JobCancelledError("Cancelled") from None
            if time.monotonic() >= deadline:
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

    def _terminate(self, process: subprocess.Popen[str]) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            with contextlib.suppress(OSError):
                process.terminate()
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                with contextlib.suppress(OSError):
                    process.kill()
            process.wait(timeout=2.0)

    def _capture(
        self, args: list[str], *, timeout: int = DEFAULT_TIMEOUT_SECONDS
    ) -> tuple[str, str]:
        run_args, script_dir = _filter_script_args(args)
        try:
            binary = find_binary(run_args[0])
            if binary is None:
                raise IngestError(
                    f"{run_args[0]} is not available. Place it next to the executable."
                )
            if self.cancel_event is not None and self.cancel_event.is_set():
                raise JobCancelledError("Cancelled")
            self._emit("debug", "$ " + " ".join([Path(binary).name, *run_args[1:]]))
            process = subprocess.Popen(
                [binary, *run_args[1:]],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            deadline = time.monotonic() + max(1, timeout)
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.15)
                    break
                except subprocess.TimeoutExpired:
                    if self.cancel_event is not None and self.cancel_event.is_set():
                        self._terminate(process)
                        raise JobCancelledError("Cancelled") from None
                    if time.monotonic() >= deadline:
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


def _filter_script_args(args: list[str]) -> tuple[list[str], Path | None]:
    """Move a large filter graph to ``-filter_complex_script``.

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
    path.write_text(graph, encoding="utf-8")
    updated = [
        *args[:index],
        "-filter_complex_script",
        str(path),
        *args[index + 2 :],
    ]
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
