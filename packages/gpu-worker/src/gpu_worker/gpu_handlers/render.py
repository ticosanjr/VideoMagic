"""NVENC master render and Short micro-clip handlers."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gpu_worker.gpu_handlers.common import (
    _escape_filter_path,
    _ffmpeg,
    _run,
    _run_in,
    nvenc_args,
    nvenc_available,
)
from gpu_worker.handlers import Handler, HandlerError
from gpu_worker.progress import report

if TYPE_CHECKING:
    from gpu_worker.settings import Settings

def make_render_nvenc_handler(settings: Settings) -> Handler:
    """Encode one assembled video with NVENC, optionally burning ASS subtitles."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("render_nvenc requires a base video artifact")
        ffmpeg = _ffmpeg(settings)
        if not nvenc_available(ffmpeg):
            raise HandlerError("FFmpeg does not expose h264_nvenc")
        base = input_paths[0]
        ass_path = Path(str(params.get("ass_path") or "")).expanduser()
        if not ass_path.is_file():
            ass_path = next(
                (path for path in input_paths[1:] if path.suffix.casefold() == ".ass"),
                Path(),
            )
        output = work_dir / str(params.get("output_name") or "render.mp4")
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(base)]
        filters: list[str] = []
        width = int(params.get("width") or 0)
        height = int(params.get("height") or 0)
        fps = int(params.get("fps") or 0)
        if width and height:
            filters.append(
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
            )
        if fps:
            filters.append(f"fps={fps}")
        if ass_path.is_file():
            fonts_dir = _materialize_fonts(params.get("font_paths"), work_dir)
            ass_filter = f"ass='{_escape_filter_path(ass_path)}'"
            if fonts_dir is not None:
                ass_filter += f":fontsdir='{_escape_filter_path(fonts_dir)}'"
            filters.append(ass_filter)
        # NVENC only consumes 8-bit 4:2:0. This explicit format forces CPU
        # decode/conversion for 10-bit 4:2:2 and HDR sources before encoding.
        filters.append("format=yuv420p")
        if filters:
            command.extend(["-vf", ",".join(filters)])
        command.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "h264_nvenc",
                *nvenc_args(ffmpeg),
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                str(params.get("audio_bitrate") or "192k"),
                "-movflags",
                "+faststart",
            ]
        )
        if params.get("duration"):
            command.extend(["-t", f"{float(params['duration']):.3f}"])
        command.append(str(output))
        report("encoding with NVENC", 20)
        _run(command)
        report("finalizing", 95)
        if not output.is_file():
            raise HandlerError("render_nvenc did not create the output video")
        return [output]

    return handler


def make_ffmpeg_transcode_handler(settings: Settings) -> Handler:
    """Loop/trim/filter a still or clip with the worker FFmpeg."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("ffmpeg_transcode requires an input artifact")
        source = input_paths[0]
        output_name = str(params.get("output_name") or "transcode.mp4")
        output = work_dir / output_name
        filter_chain = str(params.get("filter") or "").strip()
        argv = [_ffmpeg(settings), "-hide_banner", "-loglevel", "error", "-y"]
        if params.get("still", True):
            argv.extend(["-loop", "1"])
        argv.extend(["-i", str(source)])
        duration = params.get("duration_sec")
        if duration:
            argv.extend(["-t", f"{float(duration):.3f}"])
        if filter_chain:
            argv.extend(["-vf", filter_chain])
        fps = params.get("fps")
        if fps:
            argv.extend(["-r", str(int(fps))])
        if params.get("audio"):
            argv.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            argv.append("-an")
        argv.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                str(int(params.get("crf") or 18)),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        report("transcoding", 20)
        _run(argv)
        if not output.is_file() or output.stat().st_size == 0:
            raise HandlerError("ffmpeg_transcode produced no output")
        return [output]

    return handler


def _materialize_fonts(values: object, work_dir: Path) -> Path | None:
    """Copy uploaded font files into one directory for ``fontsdir``."""

    if not isinstance(values, (list, tuple)):
        return None
    fonts = [
        Path(str(item)).expanduser()
        for item in values
        if str(item).strip() and Path(str(item)).expanduser().is_file()
    ]
    if not fonts:
        return None
    target = Path(work_dir) / "fonts"
    target.mkdir(parents=True, exist_ok=True)
    for font in fonts:
        destination = target / font.name
        if not destination.is_file():
            shutil.copy2(font, destination)
    return target


def make_short_render_handler(settings: Settings) -> Handler:
    """Execute tokenised micro-clip/concat/final FFmpeg commands."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("short_render requires input artifacts")
        tokens = {
            f"__IN{index}__": str(path) for index, path in enumerate(input_paths)
        }
        fonts_dir = _materialize_fonts(params.get("font_paths"), work_dir)

        def replace(value: str) -> str:
            for token, path in tokens.items():
                value = value.replace(token, path)
            return value

        def replace_filter(value: str) -> str:
            for token, path in tokens.items():
                value = value.replace(token, _escape_filter_path(Path(path)))
            if fonts_dir is not None:
                value = re.sub(
                    r"(ass='[^']*')",
                    rf"\1:fontsdir='{_escape_filter_path(fonts_dir)}'",
                    value,
                )
            return value

        ffmpeg = _ffmpeg(settings)
        cache_root = work_dir.parent.parent / "short_segment_cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        raw_segments = params.get("segments") or []
        total_segments = max(1, len(raw_segments))
        pending: list[tuple[int, dict[str, Any], str, Path]] = []
        for index, segment in enumerate(raw_segments, start=1):
            if not isinstance(segment, dict):
                raise HandlerError("short_render segment must be an object")
            output_name = str(segment.get("output") or f"seg_{index:04d}.mp4")
            cached = cache_root / f"{segment.get('cache_key') or index}.mp4"
            if cached.is_file() and cached.stat().st_size > 0:
                target = work_dir / output_name
                try:
                    os.link(cached, target)
                except OSError:
                    shutil.copy2(cached, target)
                continue
            pending.append((index, segment, output_name, cached))

        def render_segment(
            index: int,
            segment: dict[str, Any],
            output_name: str,
            cached: Path,
        ) -> None:
            report(
                f"rendering segment {index}/{total_segments}",
                5 + round(80 * (index - 1) / total_segments),
            )
            script = work_dir / f"segment_{index:04d}.ffscript"
            script.write_text(
                replace_filter(str(segment.get("filter") or "")), encoding="utf-8"
            )
            argv = [str(item) for item in segment.get("argv") or []]
            if not argv:
                raise HandlerError("short_render segment has no command")
            argv[0] = ffmpeg
            argv = [
                replace(item).replace(f"__SCRIPT_{index}__", str(script))
                for item in argv
            ]
            if any("__IN" in item or "__SCRIPT" in item for item in argv):
                raise HandlerError("short_render left an unresolved placeholder")
            _run_in(argv, work_dir)
            segment_output = work_dir / output_name
            if not segment_output.is_file() or segment_output.stat().st_size == 0:
                raise HandlerError(
                    f"short_render segment {index} produced no output"
                )
            if not cached.is_file():
                try:
                    os.link(segment_output, cached)
                except OSError:
                    shutil.copy2(segment_output, cached)

        try:
            workers = int(os.environ.get("VF_SHORT_SEGMENT_WORKERS", "2"))
        except ValueError:
            workers = 2
        workers = max(1, min(workers, 8, max(1, len(pending))))
        if workers == 1:
            for item in pending:
                render_segment(*item)
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(render_segment, *item) for item in pending]
                try:
                    for future in as_completed(futures):
                        future.result()
                except BaseException:
                    for future in futures:
                        future.cancel()
                    raise
        report("concatenating and encoding", 92)
        names = [str(item) for item in params.get("concat_names") or []]
        if not names:
            raise HandlerError("short_render produced no micro-clips")
        concat = work_dir / "concat.txt"
        concat.write_text(
            "\n".join(f"file '{name}'" for name in names) + "\n",
            encoding="utf-8",
        )
        final_script = work_dir / "final.ffscript"
        final_script.write_text(
            replace_filter(str(params.get("final_filter") or "")), encoding="utf-8"
        )
        final_argv = [str(item) for item in params.get("final_argv") or []]
        if not final_argv:
            raise HandlerError("short_render has no final command")
        final_argv[0] = ffmpeg
        final_argv = [
            replace(item)
            .replace("__CONCAT__", str(concat))
            .replace("__SCRIPT_FINAL__", str(final_script))
            for item in final_argv
        ]
        if any("__IN" in item or "__SCRIPT" in item or "__CONCAT__" in item for item in final_argv):
            raise HandlerError("short_render left an unresolved placeholder")
        _run_in(final_argv, work_dir)
        output = work_dir / str(params.get("output_name") or "short.mp4")
        if not output.is_file():
            raise HandlerError("short_render finished without an output file")
        return [output]

    return handler
