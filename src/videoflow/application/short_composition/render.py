"""Compose and execute the hybrid Short render pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from videoflow.application.short_composition.geometry import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    CanvasRegion,
    CropBox,
    FaceBox,
    crop_for_panel,
    layout_geometry,
)
from videoflow.application.short_composition.plan import (
    camera_size,
    overlapping_scenes,
)
from videoflow.application.short_composition.tracking import (
    median_face,
)
from videoflow.core.media_contract import PIPELINE_SCHEMA_VERSION
from videoflow.domain.errors import IngestError
from videoflow.domain.scenes import SceneEntry, ScenesManifest
from videoflow.domain.short_composition import ShortCompositionPlan

DEFAULT_LOUDNORM = "I=-14:TP=-1.5:LRA=9"
DEFAULT_CRF = 19
DEFAULT_PRESET = "p5"
SFX_VOLUME_DB = -18.0
_NVENC_CACHE: dict[str, bool] = {}
_DIVIDER = 4


@dataclass(frozen=True, slots=True)
class SegmentRender:
    seg_id: str
    source_start: float
    source_end: float
    layout: str
    face_crop: CropBox
    screen_crop: CropBox | None = None
    screen_separate: bool = False
    broll_path: Path | None = None
    broll_start: float = 0.0
    divider: bool = True
    has_audio: bool = True

    @property
    def duration(self) -> float:
        return max(0.001, self.source_end - self.source_start)


@dataclass
class RenderCommands:
    inputs: list[Path]
    segments: list[dict[str, object]] = field(default_factory=list)
    concat_names: list[str] = field(default_factory=list)
    final_argv: list[str] = field(default_factory=list)
    final_filter: str = ""
    output_name: str = "short.mp4"
    work_dir: Path | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "segments": self.segments,
            "concat_names": list(self.concat_names),
            "final_argv": list(self.final_argv),
            "final_filter": self.final_filter,
            "output_name": self.output_name,
        }

    def input_tokens(self) -> dict[str, str]:
        return {f"__IN{index}__": str(path) for index, path in enumerate(self.inputs)}


@dataclass
class SfxRenderCue:
    path: Path
    time_sec: float
    volume_db: float = SFX_VOLUME_DB


def safe_output_name(
    value: str,
    *,
    default: str,
    suffix: str,
) -> str:
    name = Path(str(value or default)).name
    if name in {"", ".", ".."}:
        name = default
    if not name.casefold().endswith(suffix.casefold()):
        name = f"{name}{suffix}"
    return name


def nvenc_available(ffmpeg: str = "ffmpeg") -> bool:
    """Return whether the local FFmpeg can really encode with h264_nvenc."""

    cached = _NVENC_CACHE.get(ffmpeg)
    if cached is not None:
        return cached
    from videoflow.core.nvenc import nvenc_available as probe

    available = probe(ffmpeg)
    _NVENC_CACHE[ffmpeg] = available
    return available


def _even(value: int) -> int:
    return int(value) - (int(value) % 2)


def _crop_filter(crop: CropBox) -> str:
    width = max(2, _even(crop.width))
    height = max(2, _even(crop.height))
    x = max(0, min(int(crop.x), CANVAS_WIDTH * 16))
    y = max(0, min(int(crop.y), CANVAS_HEIGHT * 16))
    return f"crop={width}:{height}:{x}:{y}"


def _panel_filter(panel: CanvasRegion) -> str:
    return (
        f"scale={_even(panel.width)}:{_even(panel.height)}:flags=lanczos,"
        f"setsar=1,format=yuv420p"
    )


def _fit_panel(panel: CanvasRegion) -> str:
    return (
        f"scale={_even(panel.width)}:{_even(panel.height)}:"
        "force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={_even(panel.width)}:{_even(panel.height)},setsar=1,format=yuv420p"
    )


def segment_filter(
    segment: SegmentRender,
    *,
    fps: int = 30,
    audio_label: str = "0:a",
) -> str:
    geometry = layout_geometry(segment.layout)
    face_panel = geometry.face
    parts: list[str] = []
    if segment.screen_crop is not None and not segment.screen_separate:
        parts.append("[0:v]split=2[face_src][screen_src]")
        face_src, screen_src = "[face_src]", "[screen_src]"
    elif segment.screen_crop is not None:
        face_src, screen_src = "[0:v]", "[1:v]"
    else:
        face_src, screen_src = "[0:v]", ""
    face_chain = (
        f"{face_src}{_crop_filter(segment.face_crop)},"
        f"{_panel_filter(face_panel)},fps={int(fps)}[face]"
    )
    parts.append(face_chain)
    if segment.layout == "FULL_FACE":
        parts.append("[face]null[v]")
    elif segment.layout == "SPLIT_BROLL":
        broll_panel = geometry.broll or geometry.face
        parts.append(
            f"[1:v]fps={int(fps)},{_fit_panel(broll_panel)}[broll]"
        )
        parts.append("[face][broll]vstack=inputs=2[v0]")
        if face_panel.height + broll_panel.height < CANVAS_HEIGHT:
            parts.append(
                f"[v0]pad={CANVAS_WIDTH}:{CANVAS_HEIGHT}:0:0:color=black[v0]"
            )
        if segment.divider:
            y = geometry.broll.y - _DIVIDER // 2 if geometry.broll else face_panel.bottom
            parts.append(
                f"[v0]drawbox=x=0:y={max(0, y)}:w={CANVAS_WIDTH}:h={_DIVIDER}:"
                "color=white@0.85:t=fill[v]"
            )
        else:
            parts.append("[v0]null[v]")
    else:
        screen_panel = geometry.screen or geometry.face
        parts.append(
            f"{screen_src}{_crop_filter(segment.screen_crop or segment.face_crop)},"
            f"{_panel_filter(screen_panel)},fps={int(fps)}[screen]"
        )
        parts.append("[screen][face]vstack=inputs=2[vstack]")
        if screen_panel.height + face_panel.height < CANVAS_HEIGHT:
            parts.append(
                f"[vstack]pad={CANVAS_WIDTH}:{CANVAS_HEIGHT}:0:0:color=black[v]"
            )
        else:
            parts.append("[vstack]null[v]")
    parts.append(
        f"[{audio_label}]asetpts=PTS-STARTPTS,aresample=48000[a]"
    )
    return ";\n".join(parts)


def _median_face(scenes: Sequence[SceneEntry]) -> FaceBox | None:
    return median_face(
        [
            FaceBox(
                cx=scene.face_bbox_norm.cx,
                cy=scene.face_bbox_norm.cy,
                w=scene.face_bbox_norm.w,
                h=scene.face_bbox_norm.h,
            )
            if scene.face_bbox_norm is not None
            else None
            for scene in scenes
        ]
    )


def _screen_geometry(
    manifest: ScenesManifest,
    *,
    cam_side: str,
) -> tuple[int, int, int]:
    width = int(manifest.resolution.get("w") or 1920)
    height = int(manifest.resolution.get("h") or 1080)
    if manifest.source_topology == "dual_canvas":
        half = max(1, width // 2)
        offset = half if str(cam_side).lower() == "left" else 0
        return half, height, offset
    return width, height, 0


def _cam_offset(manifest: ScenesManifest, *, cam_side: str, screen_offset: int) -> int:
    if manifest.source_topology != "dual_canvas":
        return 0
    width = int(manifest.resolution.get("w") or 1920)
    half = max(1, width // 2)
    return 0 if str(cam_side).lower() == "left" else half


def build_segment_renders(
    plan: ShortCompositionPlan,
    manifest: ScenesManifest,
    *,
    smooth_track: bool = False,
    cam_side: str = "right",
    broll_paths: dict[str, Path] | None = None,
    screen_separate: bool = False,
) -> list[SegmentRender]:
    scenes = sorted(manifest.scenes, key=lambda item: item.start_sample)
    cam_w, cam_h = camera_size(manifest)
    screen_w, screen_h, screen_offset = _screen_geometry(manifest, cam_side=cam_side)
    cam_offset = _cam_offset(manifest, cam_side=cam_side, screen_offset=screen_offset)
    renders: list[SegmentRender] = []
    for segment in plan.segments:
        rel_start = segment.rel_start + plan.start
        rel_end = segment.rel_end + plan.start
        touched = overlapping_scenes(scenes, rel_start, rel_end)
        broll_path = None
        if segment.layout == "SPLIT_BROLL" and segment.broll_source is not None:
            raw = (broll_paths or {}).get(segment.broll_source.path)
            if raw is not None and Path(raw).is_file():
                broll_path = Path(raw)
        layout = segment.layout
        render_zoom = segment.face_zoom
        if layout == "SPLIT_BROLL" and broll_path is None:
            layout = "FULL_FACE"
            render_zoom = 1.12
        geometry = layout_geometry(layout)
        face = _median_face(touched)
        face_crop = crop_for_panel(
            cam_w=cam_w,
            cam_h=cam_h,
            panel=geometry.face,
            face=face,
            zoom=render_zoom,
        )
        face_crop = CropBox(
            x=face_crop.x + cam_offset,
            y=face_crop.y,
            width=face_crop.width,
            height=face_crop.height,
        )
        screen_crop: CropBox | None = None
        if geometry.screen is not None:
            screen_crop = crop_for_panel(
                cam_w=screen_w,
                cam_h=screen_h,
                panel=geometry.screen,
                face=None,
            )
            screen_crop = CropBox(
                x=screen_crop.x + screen_offset,
                y=screen_crop.y,
                width=screen_crop.width,
                height=screen_crop.height,
            )
        if smooth_track and len(touched) > 1:
            for index, scene in enumerate(touched):
                piece_start = max(rel_start, scene.start_sec)
                piece_end = min(rel_end, scene.end_sec)
                if piece_end <= piece_start:
                    continue
                piece_crop = crop_for_panel(
                    cam_w=cam_w,
                    cam_h=cam_h,
                    panel=geometry.face,
                    face=(
                        FaceBox(
                            cx=scene.face_bbox_norm.cx,
                            cy=scene.face_bbox_norm.cy,
                            w=scene.face_bbox_norm.w,
                            h=scene.face_bbox_norm.h,
                        )
                        if scene.face_bbox_norm is not None
                        else None
                    ),
                    zoom=render_zoom,
                )
                renders.append(
                    SegmentRender(
                        seg_id=f"{segment.seg_id}_{index + 1}",
                        source_start=piece_start,
                        source_end=piece_end,
                        layout=layout,
                        face_crop=CropBox(
                            x=piece_crop.x + cam_offset,
                            y=piece_crop.y,
                            width=piece_crop.width,
                            height=piece_crop.height,
                        ),
                        screen_crop=screen_crop,
                        screen_separate=screen_separate,
                        broll_path=broll_path,
                        divider=True,
                    )
                )
            continue
        renders.append(
            SegmentRender(
                seg_id=segment.seg_id,
                source_start=rel_start,
                source_end=rel_end,
                layout=layout,
                face_crop=face_crop,
                screen_crop=screen_crop,
                screen_separate=screen_separate,
                broll_path=broll_path,
                divider=True,
            )
        )
    return renders


def _filter_path(path: Path) -> str:
    return (
        str(path)
        .replace("\\", "/")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )


def _token(index: int) -> str:
    return f"__IN{index}__"


def _segment_cache_key(
    *,
    source: Path,
    segment: SegmentRender,
    script: str,
    fps: int,
    encoder: str,
) -> str:
    try:
        stat = Path(source).stat()
        fingerprint = f"{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:
        fingerprint = "missing"
    payload = {
        "pipeline_schema_version": PIPELINE_SCHEMA_VERSION,
        "source": str(source),
        "fingerprint": fingerprint,
        "start": round(segment.source_start, 6),
        "end": round(segment.source_end, 6),
        "layout": segment.layout,
        "broll": str(segment.broll_path or ""),
        "filter": script,
        "fps": int(fps),
        "encoder": encoder,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:20]


def build_commands(
    renders: Sequence[SegmentRender],
    *,
    source: Path,
    screen: Path | None = None,
    captions: Path | None = None,
    sfx: Sequence[SfxRenderCue] = (),
    output_name: str = "short.mp4",
    fps: int = 30,
    encoder: str = "libx264",
    fade_start: float = 0.0,
    fade_ms: int = 80,
    padding_sec: float = 0.0,
    loudnorm: str = DEFAULT_LOUDNORM,
    fontsdir: str | None = None,
) -> RenderCommands:
    """Build tokenised FFmpeg commands for local or remote execution."""

    paths: list[Path] = [Path(source)]
    index_by_path: dict[str, int] = {str(Path(source)): 0}
    if screen is not None:
        screen_path = Path(screen)
        if str(screen_path) not in index_by_path:
            paths.append(screen_path)
            index_by_path[str(screen_path)] = len(paths) - 1
    for render in renders:
        if render.broll_path is None:
            continue
        key = str(render.broll_path)
        if key not in index_by_path:
            paths.append(Path(render.broll_path))
            index_by_path[key] = len(paths) - 1
    captions_index = None
    if captions is not None:
        caption_path = Path(captions)
        if str(caption_path) not in index_by_path:
            paths.append(caption_path)
            index_by_path[str(caption_path)] = len(paths) - 1
        captions_index = index_by_path[str(caption_path)]
    sfx_entries: list[tuple[SfxRenderCue, int]] = []
    for cue in sfx:
        path = Path(cue.path)
        if str(path) not in index_by_path:
            paths.append(path)
            index_by_path[str(path)] = len(paths) - 1
        sfx_entries.append((cue, index_by_path[str(path)]))

    commands: list[dict[str, object]] = []
    concat_names: list[str] = []
    for index, segment in enumerate(renders, start=1):
        name = f"seg_{index:04d}.mp4"
        argv = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{segment.source_start:.6f}",
            "-t",
            f"{segment.duration:.6f}",
            "-i",
            _token(0),
        ]
        audio_index = 0
        if segment.broll_path is not None:
            broll_index = index_by_path[str(segment.broll_path)]
            argv.extend(
                [
                    "-stream_loop",
                    "-1",
                    "-ss",
                    f"{segment.broll_start:.6f}",
                    "-t",
                    f"{segment.duration:.6f}",
                    "-i",
                    _token(broll_index),
                ]
            )
            audio_index = 1
        elif segment.screen_crop is not None and segment.screen_separate:
            if screen is None:
                raise IngestError("dual-file Short render needs a screen video")
            screen_index = index_by_path[str(Path(screen))]
            argv.extend(["-i", _token(screen_index)])
            audio_index = 1
        if not segment.has_audio:
            argv.extend(
                [
                    "-f",
                    "lavfi",
                    "-t",
                    f"{segment.duration:.6f}",
                    "-i",
                    "anullsrc=r=48000:cl=stereo",
                ]
            )
            audio_index = 2 if audio_index == 1 else 1
        script = segment_filter(segment, fps=fps, audio_label=f"{audio_index}:a")
        if encoder == "nvenc":
            video_codec = [
                "-c:v",
                "h264_nvenc",
                "-preset",
                "p4",
                "-rc",
                "vbr",
                "-cq",
                "20",
                "-b:v",
                "0",
                "-spatial-aq",
                "1",
                "-temporal-aq",
                "1",
                "-pix_fmt",
                "yuv420p",
            ]
        else:
            video_codec = [
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
            ]
        argv.extend(
            [
                "-filter_complex_script",
                f"__SCRIPT_{index}__",
                "-map",
                "[v]",
                "-map",
                "[a]",
                *video_codec,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-r",
                str(int(fps)),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                name,
            ]
        )
        cache_key = _segment_cache_key(
            source=source,
            segment=segment,
            script=script,
            fps=fps,
            encoder=encoder,
        )
        commands.append(
            {
                "argv": argv,
                "filter": script,
                "output": name,
                "cache_key": cache_key,
            }
        )
        concat_names.append(name)

    fade_start_abs = max(0.0, float(fade_start))
    final_filter_parts = []
    video_chain = (
        f"[0:v]ass='{_token(captions_index)}'"
        + (
            f":fontsdir='{_filter_path(Path(fontsdir))}'"
            if fontsdir
            else ""
        )
        if captions_index is not None
        else "[0:v]null"
    )
    if padding_sec > 0:
        video_chain += f",tpad=stop_mode=clone:stop_duration={padding_sec:.3f}"
    final_filter_parts.append(f"{video_chain}[v]")
    audio_chain = f"[0:a]loudnorm={loudnorm}"
    if padding_sec > 0:
        audio_chain += f",apad=pad_dur={padding_sec:.3f}"
    audio_chain += (
        f",afade=t=out:st={fade_start_abs:.3f}:d={max(0.0, fade_ms / 1000.0):.3f}"
    )
    if sfx_entries:
        labels = []
        for position, (cue, _input_index) in enumerate(sfx_entries, start=1):
            delay = max(0, round(cue.time_sec * 1000.0))
            final_filter_parts.append(
                f"[{position}:a]volume={cue.volume_db:.1f}dB,"
                f"adelay={delay}|{delay}[s{position}]"
            )
            labels.append(f"[s{position}]")
        final_filter_parts.append(
            f"{audio_chain}[a0];"
            + "[a0]"
            + "".join(labels)
            + f"amix=inputs={len(labels) + 1}:duration=first:"
            "dropout_transition=0[a]"
        )
    else:
        final_filter_parts.append(f"{audio_chain}[a]")
    final_argv = [
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
        "__CONCAT__",
    ]
    for _cue, input_index in sfx_entries:
        final_argv.extend(["-i", _token(input_index)])
    if encoder == "nvenc":
        codec = [
            "-c:v",
            "h264_nvenc",
            "-preset",
            DEFAULT_PRESET,
            "-tune",
            "hq",
            "-rc",
            "vbr",
            "-cq",
            str(DEFAULT_CRF),
            "-b:v",
            "0",
            "-spatial-aq",
            "1",
            "-temporal-aq",
            "1",
            "-rc-lookahead",
            "20",
            "-pix_fmt",
            "yuv420p",
        ]
    else:
        codec = [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(DEFAULT_CRF),
        ]
    final_argv.extend(
        [
            "-filter_complex_script",
            "__SCRIPT_FINAL__",
            "-map",
            "[v]",
            "-map",
            "[a]",
            *codec,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            output_name,
        ]
    )
    return RenderCommands(
        inputs=paths,
        segments=commands,
        concat_names=concat_names,
        final_argv=final_argv,
        final_filter=";\n".join(final_filter_parts),
        output_name=output_name,
    )


def _replace_tokens(value: str, tokens: dict[str, str]) -> str:
    for token, path in tokens.items():
        value = value.replace(token, path)
    return value


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _replace_filter_tokens(value: str, tokens: dict[str, str]) -> str:
    for token, path in tokens.items():
        value = value.replace(token, _escape_filter_path(Path(path)))
    return value


def execute_commands(
    commands: RenderCommands,
    work_dir: Path,
    *,
    ffmpeg: str = "ffmpeg",
    runner: Callable[[list[str], Path], None] | None = None,
    check_cancel: Callable[[], None] | None = None,
    segment_cache: Path | None = None,
    segment_workers: int | None = None,
) -> Path:
    """Run micro-clips, concat, and finalisation in one work directory.

    Independent micro-clips render in parallel when a real subprocess runner is
    used. Custom runners stay sequential so tests and callers keep deterministic
    ordering. Set ``VF_SHORT_SEGMENT_WORKERS`` to tune the pool.
    """

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    tokens = commands.input_tokens()
    run = runner or _run
    cache_root = Path(segment_cache).expanduser() if segment_cache is not None else None
    if cache_root is not None:
        cache_root.mkdir(parents=True, exist_ok=True)
    pending: list[tuple[int, dict[str, object], str, Path | None]] = []
    for index, segment in enumerate(commands.segments, start=1):
        output_name = str(segment.get("output") or f"seg_{index:04d}.mp4")
        cached = (
            cache_root / f"{segment.get('cache_key') or index}.mp4"
            if cache_root is not None
            else None
        )
        if cached is not None and cached.is_file() and cached.stat().st_size > 0:
            target = work / output_name
            try:
                os.link(cached, target)
            except OSError:
                shutil.copy2(cached, target)
            continue
        pending.append((index, segment, output_name, cached))

    def render_segment(
        index: int,
        segment: dict[str, object],
        output_name: str,
        cached: Path | None,
    ) -> None:
        if check_cancel is not None:
            check_cancel()
        script_path = work / f"segment_{index:04d}.ffscript"
        script_path.write_text(
            _replace_filter_tokens(str(segment["filter"]), tokens), encoding="utf-8"
        )
        argv = [str(item) for item in segment["argv"]]  # type: ignore[union-attr]
        argv[0] = ffmpeg
        argv = [
            _replace_tokens(item, tokens).replace(
                f"__SCRIPT_{index}__", str(script_path)
            )
            for item in argv
        ]
        run(argv, work)
        segment_output = work / output_name
        if not segment_output.is_file() or segment_output.stat().st_size == 0:
            raise IngestError(
                f"Short render segment {index} produced no output: {segment_output}"
            )
        if cached is not None:
            try:
                os.link(segment_output, cached)
            except OSError:
                shutil.copy2(segment_output, cached)

    if segment_workers is None:
        if runner is not None:
            segment_workers = 1
        else:
            try:
                segment_workers = int(os.environ.get("VF_SHORT_SEGMENT_WORKERS", "2"))
            except ValueError:
                segment_workers = 2
    workers = max(1, min(int(segment_workers), 8, max(1, len(pending))))
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
    concat_path = work / "concat.txt"
    concat_path.write_text(
        "\n".join(
            f"file '{name}'" for name in commands.concat_names
        )
        + "\n",
        encoding="utf-8",
    )
    final_script = work / "final.ffscript"
    final_script.write_text(
        _replace_filter_tokens(commands.final_filter, tokens), encoding="utf-8"
    )
    final_argv = [str(item) for item in commands.final_argv]
    final_argv[0] = ffmpeg
    final_argv = [
        _replace_tokens(item, tokens).replace("__CONCAT__", str(concat_path)).replace(
            "__SCRIPT_FINAL__", str(final_script)
        )
        for item in final_argv
    ]
    if check_cancel is not None:
        check_cancel()
    run(final_argv, work)
    output = work / commands.output_name
    if not output.is_file():
        raise IngestError(f"Short render finished without an output file: {output}")
    return output


def _run(argv: list[str], cwd: Path) -> None:
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise IngestError(
            "Short render command failed: "
            + (tail[-1][:500] if tail else f"exit {completed.returncode}"),
            command=argv,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )


def move_output(source: Path, destination: Path) -> Path:
    target = Path(destination).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    shutil.move(str(source), str(target))
    return target


def write_render_report(
    commands: RenderCommands,
    *,
    path: Path,
    placement: str,
    degraded: bool,
    reason: str,
    encoder: str,
    output: Path,
) -> dict[str, object]:
    report = {
        "ok": True,
        "placement": placement,
        "degraded": degraded,
        "degraded_reason": reason,
        "encoder": encoder,
        "output": str(output),
        "segment_count": len(commands.segments),
        "inputs": [str(item) for item in commands.inputs],
        "filters": {
            "segments": [str(item["filter"]) for item in commands.segments],
            "final": commands.final_filter,
        },
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


__all__ = [
    "DEFAULT_CRF",
    "DEFAULT_LOUDNORM",
    "DEFAULT_PRESET",
    "RenderCommands",
    "SegmentRender",
    "SfxRenderCue",
    "build_commands",
    "build_segment_renders",
    "execute_commands",
    "move_output",
    "safe_output_name",
    "nvenc_available",
    "segment_filter",
    "write_render_report",
]
