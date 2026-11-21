"""Short renderer (split further in Phase 3)."""

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




class ShortsMixin:
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
                        "loudnorm=I=-15.5:TP=-2.0:LRA=9,"
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

