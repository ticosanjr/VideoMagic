"""VideoFlow 2.90 vision tools: captions, mattes, upscale, motion, and B-roll."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

from . import commands, storage
from .errors import (
    InputNotFoundError,
    InvalidArgumentError,
    MissingCommandError,
    OutputNotProducedError,
    RemoteResultError,
)
from .router import RouterBridge

ROUTER = RouterBridge()
MOTION_ENGINES = {"remotion", "manim", "ffmpeg", "html", "hyperframes"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MOTIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right"}
BROLL_ASPECTS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "3:4": (1080, 1440),
    "2:3": (1080, 1620),
    "1:1": (1080, 1080),
}


def transcribe_word_aligned(
    project_id: str,
    audio_path: str,
    language: str = "pt",
    style: str = "shorts_karaoke",
) -> dict[str, Any]:
    """Transcribe audio to word-aligned captions in JSON, SRT, and ASS."""

    tool = "transcribe_word_aligned"
    source = _ensure_input(audio_path, "audio_path")
    if not language or not str(language).strip():
        raise InvalidArgumentError("language must not be empty", details={"argument": "language"})
    if not style or not str(style).strip():
        raise InvalidArgumentError("style must not be empty", details={"argument": "style"})

    model_marker = os.environ.get("VF_WHISPER_MODEL") or os.environ.get("VF_STABLE_TS_MODEL")
    key = storage.cache_key(
        tool,
        storage.file_fingerprint(source),
        language,
        style,
        model_marker or "",
    )
    transcript_relative = "captions/transcript.json"
    caption_relatives = ("captions.srt", "captions.ass")
    cached_transcript = storage.cached_asset(project_id, transcript_relative, key)
    cached_captions = [
        storage.cached_asset(project_id, relative, key) for relative in caption_relatives
    ]
    if cached_transcript is not None and all(cached_captions):
        records = [cached_transcript, *[record for record in cached_captions if record]]
        payload = _assets_payload(tool, project_id, records, mode="cache")
        payload["transcript"] = str(cached_transcript.path)
        payload["language"] = language
        payload["style"] = style
        return payload

    segments: list[dict[str, Any]] | None = None
    backend = ""
    if ROUTER.health("asr"):
        try:
            segments = _transcribe_remote(source, language)
            backend = "remote:asr"
        except Exception:  # noqa: BLE001 - the local fallback is the contract
            segments = None

    if segments is None:
        binary = commands.resolve_binary(
            "whisper-cli",
            "whisper-cpp",
            "whisper",
            env="VF_WHISPER_BIN",
        )
        if binary:
            segments = _transcribe_with_whisper(binary, source, language)
            backend = "local:whisper.cpp"
        elif _stable_whisper_available():
            segments = _transcribe_with_stable_whisper(source, language)
            backend = "local:stable-ts"
        else:
            raise MissingCommandError(
                "whisper.cpp was not found and stable-ts is not installed; "
                "set VF_WHISPER_BIN or install stable-ts",
                details={
                    "env": ["VF_WHISPER_BIN", "VF_WHISPER_MODEL"],
                    "capability": "asr",
                },
            )

    transcript = {
        "version": 1,
        "language": language,
        "style": style,
        "backend": backend,
        "segments": segments,
    }
    records = [
        storage.write_output(
            project_id,
            transcript_relative,
            data=(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            kind="captions",
            license="source",
            source=backend,
            cache_key=key,
            metadata={"language": language, "style": style, "segments": len(segments)},
        ),
        storage.write_output(
            project_id,
            "captions.srt",
            data=segments_to_srt(segments).encode("utf-8"),
            kind="captions",
            license="source",
            source=backend,
            cache_key=key,
            metadata={"language": language, "style": style, "format": "srt"},
        ),
        storage.write_output(
            project_id,
            "captions.ass",
            data=segments_to_ass(segments, style=style).encode("utf-8"),
            kind="captions",
            license="source",
            source=backend,
            cache_key=key,
            metadata={"language": language, "style": style, "format": "ass"},
        ),
    ]
    payload = _assets_payload(tool, project_id, records, mode="local")
    payload["transcript"] = str(records[0].path)
    payload["language"] = language
    payload["style"] = style
    payload["segments"] = len(segments)
    return payload


def remove_background(
    project_id: str,
    input_path: str,
    is_video: bool = False,
) -> dict[str, Any]:
    """Remove an image or video background with rembg."""

    tool = "remove_background"
    source = _ensure_input(input_path, "input_path")
    if not is_video and source.suffix.lower() in VIDEO_EXTENSIONS:
        is_video = True
    key = storage.cache_key(tool, storage.file_fingerprint(source), bool(is_video))
    if is_video:
        relative = f"assets/matte/{source.stem}_alpha.webm"
    else:
        relative = f"assets/matte/{source.stem}_alpha.png"

    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    if is_video:
        _matte_video(source, target)
    else:
        _run_rembg(source, target)

    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind=("broll" if is_video else "images"),
        license="source",
        source="local:rembg",
        cache_key=key,
        metadata={"is_video": bool(is_video), "input": str(source)},
    )
    return _payload(tool, project_id, record, mode="local")


UPSCALE_MAX_DIM = 8192


def _ffprobe() -> str:
    configured = os.environ.get("VF_FFPROBE")
    if configured:
        return configured
    found = shutil.which("ffprobe")
    if found:
        return found
    raise MissingCommandError(
        "ffprobe is required for upscale validation",
        details={"env": ["VF_FFPROBE"], "executable": "ffprobe"},
    )


def _probe_stream(path: Path) -> dict[str, float]:
    try:
        probe = _ffprobe()
        result = commands.run(
            [
                probe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate",
                "-of",
                "default=noprint_wrappers=1",
                str(path),
            ]
        )
    except Exception:  # noqa: BLE001 - probe is advisory
        return {}
    values: dict[str, float] = {}
    for line in result.stdout.splitlines():
        key, _, raw = line.partition("=")
        if key in {"width", "height"}:
            try:
                values[key] = float(int(raw))
            except ValueError:
                continue
        elif key == "r_frame_rate" and "/" in raw:
            numerator, denominator = raw.split("/", 1)
            try:
                values["fps"] = float(numerator) / max(1e-9, float(denominator))
            except ValueError:
                continue
    return values


def _select_upscale_backend(requested: str) -> tuple[str, str]:
    selected = (requested or "auto").strip().lower()
    if selected not in {"auto", "remote", "realesrgan", "realesrgan_cmd", "ffmpeg"}:
        raise InvalidArgumentError(
            "backend must be auto, remote, realesrgan, realesrgan_cmd, or ffmpeg",
            details={"argument": "backend", "value": requested},
        )
    if selected == "auto":
        if ROUTER.health("upscale"):
            return "remote", ""
        if os.environ.get("VF_REALESRGAN_CMD"):
            return "realesrgan_cmd", ""
        if shutil.which("realesrgan-ncnn-vulkan"):
            return "realesrgan", ""
        return "ffmpeg", "no upscale backend is installed; using FFmpeg lanczos"
    if selected == "remote":
        if ROUTER.health("upscale"):
            return "remote", ""
        return "ffmpeg", "remote worker is unavailable; using FFmpeg lanczos"
    if selected in {"realesrgan", "realesrgan_cmd"}:
        if selected == "realesrgan_cmd" and os.environ.get("VF_REALESRGAN_CMD"):
            return "realesrgan_cmd", ""
        if shutil.which("realesrgan-ncnn-vulkan"):
            return "realesrgan", ""
        return "ffmpeg", "Real-ESRGAN is unavailable; using FFmpeg lanczos"
    return "ffmpeg", ""


def _realesrgan_video(
    source: Path,
    target: Path,
    *,
    binary: str,
    scale: int,
) -> None:
    ffmpeg = _ffmpeg()
    probe = _probe_stream(source)
    fps = float(probe.get("fps") or 30.0)
    with tempfile.TemporaryDirectory(prefix="vf-upscale-") as raw:
        root = Path(raw)
        frames = root / "frames"
        upscaled = root / "upscaled"
        frames.mkdir()
        upscaled.mkdir()
        commands.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-vsync",
                "0",
                str(frames / "frame-%08d.png"),
            ]
        )
        commands.run(
            [
                binary,
                "-i",
                str(frames),
                "-o",
                str(upscaled),
                "-s",
                str(scale),
            ]
        )
        commands.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-framerate",
                f"{fps:.6f}",
                "-i",
                str(upscaled / "frame-%08d.png"),
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "1:a?",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(target),
            ]
        )


def _upscale_ffmpeg(source: Path, target: Path, *, factor: int, is_video: bool) -> None:
    ffmpeg = _ffmpeg()
    argv = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vf",
        f"scale=iw*{factor}:ih*{factor}:flags=lanczos",
    ]
    if is_video:
        argv.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
            ]
        )
    else:
        argv.extend(["-frames:v", "1"])
    argv.append(str(target))
    commands.run(argv)


def upscale_media(
    project_id: str,
    input_path: str,
    scale: int = 2,
    backend: str = "auto",
) -> dict[str, Any]:
    """Upscale an image or video with remote compute, Real-ESRGAN, or FFmpeg."""

    tool = "upscale_media"
    source = _ensure_input(input_path, "input_path")
    try:
        factor = int(scale)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "scale must be an integer",
            details={"argument": "scale", "value": scale},
        ) from exc
    if not 1 <= factor <= 8:
        raise InvalidArgumentError(
            "scale must be between 1 and 8",
            details={"argument": "scale", "value": scale},
        )

    is_video = source.suffix.lower() in VIDEO_EXTENSIONS
    suffix = ".mp4" if is_video else (source.suffix.lower() or ".png")
    relative = f"assets/upscaled/{source.stem}_x{factor}{suffix}"
    selected, fallback_reason = _select_upscale_backend(backend)
    key = storage.cache_key(
        tool,
        storage.file_fingerprint(source),
        factor,
        selected,
        is_video,
    )
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    session, reason = selected, fallback_reason
    if selected == "remote":
        try:
            result = ROUTER.submit(
                "upscale",
                {
                    "input": str(source),
                    "scale": factor,
                    "is_video": is_video,
                    "output_name": f"upscaled{suffix}",
                },
            )
            record = _materialize_remote(
                project_id=project_id,
                relative_path=relative,
                result=result,
                capability="upscale",
                cache_key=key,
                kind=("broll" if is_video else "images"),
            )
            _validate_upscale_dimensions(target, factor)
            return _payload(tool, project_id, record, mode="remote", fallback=False)
        except Exception as exc:  # noqa: BLE001 - local fallback is the contract
            session = "ffmpeg"
            reason = f"remote upscale failed: {exc}; using FFmpeg lanczos"
    elif selected == "realesrgan_cmd":
        template = os.environ.get("VF_REALESRGAN_CMD", "")
        commands.run(
            commands.expand_template(
                template,
                {"input": str(source), "output": str(target), "scale": str(factor)},
                name="Real-ESRGAN command",
            )
        )
    elif selected == "realesrgan":
        binary = shutil.which("realesrgan-ncnn-vulkan")
        if binary is None:
            session = "ffmpeg"
            reason = "Real-ESRGAN binary disappeared; using FFmpeg lanczos"
        elif is_video:
            _realesrgan_video(source, target, binary=binary, scale=factor)
        else:
            commands.run([binary, "-i", str(source), "-o", str(target), "-s", str(factor)])
    if session == "ffmpeg" or not target.is_file():
        _upscale_ffmpeg(source, target, factor=factor, is_video=is_video)
        session = "ffmpeg"

    _require_output(target)
    if session != selected:
        fallback_key = storage.cache_key(
            tool,
            storage.file_fingerprint(source),
            factor,
            session,
            is_video,
        )
        if fallback_key != key:
            cached = storage.cached_asset(project_id, relative, fallback_key)
            if cached is not None:
                return _payload(tool, project_id, cached, mode="cache")
            key = fallback_key
    dimensions = _validate_upscale_dimensions(target, factor)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind=("broll" if is_video else "images"),
        license="source",
        source=f"{session}:upscale",
        cache_key=key,
        metadata={
            "scale": factor,
            "backend": session,
            "requested_backend": backend,
            "fallback": session == "ffmpeg",
            "fallback_reason": reason,
            "is_video": is_video,
            "dimensions": dimensions,
        },
    )
    return _payload(tool, project_id, record, mode="local", fallback=session == "ffmpeg")


def _validate_upscale_dimensions(path: Path, factor: int) -> dict[str, float]:
    if not path.is_file():
        return {}
    probe = _probe_stream(path)
    width = int(probe.get("width") or 0)
    height = int(probe.get("height") or 0)
    if width > UPSCALE_MAX_DIM or height > UPSCALE_MAX_DIM:
        path.unlink(missing_ok=True)
        raise InvalidArgumentError(
            f"upscaled output exceeds {UPSCALE_MAX_DIM}px: {width}x{height}",
            details={"width": width, "height": height, "scale": factor},
        )
    return {key: value for key, value in probe.items() if key in {"width", "height", "fps"}}


def render_motion_graphic(
    project_id: str,
    engine: str = "remotion",
    template_or_code: str = "",
    props_json: str = "{}",
    duration_sec: float = 5.0,
    alpha: bool = False,
    draft_scale: float = 1.0,
    draft: bool = False,
    width: int = 0,
    height: int = 0,
) -> dict[str, Any]:
    """Render a Remotion, Manim, FFmpeg, HTML, or HyperFrames graphic."""

    if draft:
        draft_scale = 0.5

    tool = "render_motion_graphic"
    selected = str(engine or "").strip().lower()
    if selected not in MOTION_ENGINES:
        raise InvalidArgumentError(
            f"engine must be one of: {', '.join(sorted(MOTION_ENGINES))}",
            details={"argument": "engine", "value": engine},
        )
    if not isinstance(template_or_code, str) or not template_or_code.strip():
        raise InvalidArgumentError(
            "template_or_code must not be empty",
            details={"argument": "template_or_code"},
        )
    try:
        duration = float(duration_sec)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "duration_sec must be a number",
            details={"argument": "duration_sec", "value": duration_sec},
        ) from exc
    if not 0.1 <= duration <= 600.0:
        raise InvalidArgumentError(
            "duration_sec must be between 0.1 and 600",
            details={"argument": "duration_sec", "value": duration_sec},
        )
    props = _parse_props(props_json)
    width, height = _graphic_dimensions(project_id, width, height)
    if selected in {"html", "hyperframes"}:
        return _render_web_graphic(
            project_id,
            tool=tool,
            engine=selected,
            source_value=template_or_code,
            props=props,
            duration=duration,
            alpha=alpha,
            draft_scale=draft_scale,
            width=width,
            height=height,
        )
    if selected == "ffmpeg":
        return _render_ffmpeg_graphic(
            project_id,
            tool=tool,
            graph=template_or_code,
            duration=duration,
            alpha=alpha,
            draft_scale=draft_scale,
            width=width,
            height=height,
        )

    env_key = "VF_REMOTION_CMD" if selected == "remotion" else "VF_MANIM_CMD"
    template = os.environ.get(env_key)
    if not template:
        raise MissingCommandError(
            f"set {env_key} to render {selected} graphics",
            details={"env": [env_key], "engine": selected},
        )

    key = storage.cache_key(tool, selected, template_or_code, props, duration)
    slug = _slug(Path(template_or_code).stem or selected)
    relative = f"assets/graphics/{slug}_{key[:8]}.mp4"
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="vf-motion-") as raw:
        workdir = Path(raw)
        props_file = workdir / "props.json"
        props_file.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
        argv = commands.expand_template(
            template,
            {
                "entry": template_or_code,
                "code": template_or_code,
                "props": str(props_file),
                "output": str(target),
                "duration": f"{duration:.3f}",
                "engine": selected,
            },
            name=env_key,
        )
        commands.run(argv, cwd=workdir)

    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind="graphics",
        license="generated",
        source=f"local:{selected}",
        cache_key=key,
        metadata={
            "engine": selected,
            "duration_sec": duration,
            "props": props,
            "entry": template_or_code,
        },
    )
    return _payload(tool, project_id, record, mode="local")


def _chrome() -> str:
    browser = commands.resolve_binary(
        "google-chrome",
        "chromium",
        "chromium-browser",
        "chrome",
        env="VF_CHROME_BIN",
    )
    if browser is None:
        raise MissingCommandError(
            "Chrome/Chromium is required for html motion graphics",
            details={"env": ["VF_CHROME_BIN"], "capability": "html"},
        )
    return browser


def _scaled_viewport(width: int, height: int, draft_scale: float) -> tuple[int, int]:
    try:
        scale = float(draft_scale)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "draft_scale must be a number",
            details={"argument": "draft_scale", "value": draft_scale},
        ) from exc
    if not 0.1 <= scale <= 1.0:
        raise InvalidArgumentError(
            "draft_scale must be between 0.1 and 1.0",
            details={"argument": "draft_scale", "value": draft_scale},
        )
    for name, value in (("width", width), ("height", height)):
        if not isinstance(value, int) or not 64 <= value <= 3840:
            raise InvalidArgumentError(
                f"{name} must be between 64 and 3840",
                details={"argument": name, "value": value},
            )
    return (
        max(2, round(width * scale / 2) * 2),
        max(2, round(height * scale / 2) * 2),
    )


def _web_source_digest(source: Path) -> str:
    digest = hashlib.sha256()
    files = (
        sorted(path for path in source.rglob("*") if path.is_file())
        if source.is_dir()
        else [source]
    )
    for path in files:
        relative = str(path.relative_to(source)) if source.is_dir() else source.name
        digest.update(relative.encode("utf-8"))
        with contextlib.suppress(OSError):
            digest.update(str(path.stat().st_mtime_ns).encode("ascii"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _encode_frames(
    frames: Path,
    target: Path,
    *,
    fps: int,
    duration: float,
    alpha: bool,
) -> None:
    argv = [
        _ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames / "frame-%05d.png"),
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-t",
        f"{duration:.3f}",
    ]
    if alpha:
        argv.extend(["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "24"])
    else:
        argv.extend(["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"])
    argv.append(str(target))
    commands.run(argv)


def _render_web_graphic(
    project_id: str,
    *,
    tool: str,
    engine: str,
    source_value: str,
    props: dict[str, Any],
    duration: float,
    alpha: bool,
    draft_scale: float,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Render an HTML/CSS/JS directory through headless Chromium."""

    source = Path(source_value).expanduser()
    if source.is_dir():
        entry = source / "index.html"
        if not entry.is_file():
            raise InputNotFoundError(
                f"html directory has no index.html: {source}",
                details={"path": str(source)},
            )
    elif source.suffix.lower() in {".html", ".htm"} and source.is_file():
        entry = source
    else:
        raise InputNotFoundError(
            f"html engine expects a directory or .html file: {source_value}",
            details={"path": source_value},
        )
    browser = _chrome()
    entry = entry.resolve()
    viewport_width, viewport_height = _scaled_viewport(width, height, draft_scale)
    digest = _web_source_digest(source.resolve())
    key = storage.cache_key(
        tool,
        engine,
        digest,
        props,
        duration,
        alpha,
        draft_scale,
        width,
        height,
    )
    slug = _slug(entry.stem or engine)
    extension = "webm" if alpha else "mp4"
    relative = f"assets/graphics/{slug}_{key[:8]}.{extension}"
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")

    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    fps = 30
    total = max(1, round(duration * fps))
    props_query = quote(json.dumps(props, separators=(",", ":")))
    with tempfile.TemporaryDirectory(prefix="vf-html-") as raw:
        frames = Path(raw) / "frames"
        frames.mkdir(parents=True)
        for index in range(total):
            moment = index / fps
            frame = frames / f"frame-{index:05d}.png"
            separator = "&" if "?" in entry.as_uri() else "?"
            url = (
                f"{entry.as_uri()}{separator}vf_frame={index}&vf_time={moment:.4f}"
                f"&vf_props={props_query}#t={moment:.4f}"
            )
            argv = [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--window-size={viewport_width},{viewport_height}",
                f"--virtual-time-budget={max(500, round(moment * 1000))}",
                f"--screenshot={frame}",
            ]
            if alpha:
                argv.append("--default-background-color=00000000")
            argv.append(url)
            commands.run(argv, timeout=15)
            if not frame.is_file():
                raise OutputNotProducedError(
                    f"Chromium did not capture frame {index}",
                    details={"path": str(frame)},
                )
        _encode_frames(frames, target, fps=fps, duration=duration, alpha=alpha)
    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind="graphics",
        license="generated",
        source=f"local:{engine}",
        cache_key=key,
        metadata={
            "engine": engine,
            "duration_sec": duration,
            "alpha": alpha,
            "draft_scale": draft_scale,
            "viewport": [viewport_width, viewport_height],
            "source_sha256": digest,
            "props": props,
        },
    )
    return _payload(tool, project_id, record, mode="local")


def _render_ffmpeg_graphic(
    project_id: str,
    *,
    tool: str,
    graph: str,
    duration: float,
    alpha: bool,
    draft_scale: float,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Render a plain FFmpeg filter graph on a transparent colour source."""

    viewport_width, viewport_height = _scaled_viewport(width, height, draft_scale)
    key = storage.cache_key(tool, "ffmpeg", graph, duration, alpha, draft_scale, width, height)
    slug = _slug("ffmpeg")
    extension = "webm" if alpha else "mp4"
    relative = f"assets/graphics/{slug}_{key[:8]}.{extension}"
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")
    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        _ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black@0.0:s={viewport_width}x{viewport_height}:r=30:d={duration:.3f}",
        "-vf",
        graph,
        "-t",
        f"{duration:.3f}",
    ]
    if alpha:
        argv.extend(["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "24"])
    else:
        argv.extend(["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"])
    argv.append(str(target))
    commands.run(argv)
    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind="graphics",
        license="generated",
        source="local:ffmpeg",
        cache_key=key,
        metadata={"engine": "ffmpeg", "graph": graph, "duration_sec": duration},
    )
    return _payload(tool, project_id, record, mode="local")


def _is_screen_target(value: str) -> bool:
    text = value.strip().lower()
    return text in {"screen", "desktop", "display"} or text.startswith("screen:")


@contextlib.contextmanager
def _cdp_scroll_capture(
    url: str,
    *,
    width: int,
    height: int,
    selector: str = "",
    scroll_animation: str = "",
    clip_selector: str = "",
):
    """Drive Chromium through CDP so URL captures can actually scroll."""

    import base64
    import contextlib as _contextlib
    import socket
    import subprocess
    import time
    import urllib.request

    try:
        import websocket  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001 - optional automation dependency
        raise MissingCommandError(
            "scroll_animation requires websocket-client",
            details={"env": ["VF_CHROME_BIN"], "capability": "scroll"},
        ) from exc

    browser = _chrome()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    profile = tempfile.mkdtemp(prefix="vf-cdp-")
    process = subprocess.Popen(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--window-size={width},{height}",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    socket_connection = None
    try:
        for _ in range(120):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/version", timeout=0.5
                ) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise OutputNotProducedError(
                "Chromium did not expose its debugging endpoint",
                details={"url": url},
            )
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
            targets = json.loads(response.read().decode("utf-8"))
        page = next(
            (item for item in targets if item.get("type") == "page"),
            None,
        )
        if page is None or not page.get("webSocketDebuggerUrl"):
            raise OutputNotProducedError(
                "Chromium did not expose a page target",
                details={"url": url},
            )
        socket_connection = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20)
        counter = 0

        def command(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            nonlocal counter
            counter += 1
            socket_connection.send(
                json.dumps({"id": counter, "method": method, "params": params or {}})
            )
            while True:
                message = json.loads(socket_connection.recv())
                if message.get("id") != counter:
                    continue
                if message.get("error"):
                    raise OutputNotProducedError(
                        f"Chromium CDP error: {message['error']}",
                        details={"method": method},
                    )
                return message.get("result") or {}

        command("Page.enable")
        command("Runtime.enable")
        command("Page.navigate", {"url": url})
        for _ in range(120):
            state = command(
                "Runtime.evaluate",
                {
                    "expression": "document.readyState",
                    "returnByValue": True,
                },
            )
            if (state.get("result") or {}).get("value") == "complete":
                break
            time.sleep(0.1)

        def clip_rect() -> dict[str, float] | None:
            if not clip_selector:
                return None
            expression = (
                "(() => { const e = document.querySelector("
                + json.dumps(clip_selector)
                + "); if (!e) return null;"
                " const r = e.getBoundingClientRect();"
                " return {x: r.x + window.scrollX, y: r.y + window.scrollY,"
                " width: r.width, height: r.height}; })()"
            )
            result = command(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
            )
            value = (result.get("result") or {}).get("value")
            return value if isinstance(value, dict) else None

        def capture(progress: float) -> bytes:
            ratio = max(0.0, min(1.0, float(progress)))
            if selector:
                script = (
                    f"const e = document.querySelector({json.dumps(selector)});"
                    "if (e) e.scrollIntoView({block: 'start', behavior: 'instant'});"
                )
            else:
                script = (
                    "window.scrollTo({top:"
                    "(document.documentElement.scrollHeight - window.innerHeight)"
                    f"*{ratio}, behavior:'instant'}});"
                )
            command("Runtime.evaluate", {"expression": script})
            time.sleep(0.05)
            params: dict[str, Any] = {"format": "png", "fromSurface": True}
            rect = clip_rect()
            if rect and rect.get("width") and rect.get("height"):
                params["clip"] = {
                    "x": max(0.0, float(rect["x"])),
                    "y": max(0.0, float(rect["y"])),
                    "width": float(rect["width"]),
                    "height": float(rect["height"]),
                    "scale": 1,
                }
            result = command("Page.captureScreenshot", params)
            return base64.b64decode(result.get("data", ""))

        yield capture
    finally:
        if socket_connection is not None:
            with _contextlib.suppress(Exception):
                socket_connection.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)


def _capture_screen(
    *,
    target: Path,
    mode: str,
    duration: float,
    fps: int,
    width: int,
    height: int,
) -> None:
    display = os.environ.get("DISPLAY", "").strip()
    if not display:
        raise MissingCommandError(
            "screen capture requires DISPLAY (X11); use a URL for browser capture",
            details={"env": ["DISPLAY"], "capability": "screen"},
        )
    argv = [
        _ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "x11grab",
        "-framerate",
        str(fps),
        "-video_size",
        f"{width}x{height}",
        "-i",
        display,
    ]
    if mode == "screenshot":
        argv.extend(["-frames:v", "1", str(target)])
    else:
        argv.extend(
            [
                "-t",
                f"{duration:.3f}",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                str(target),
            ]
        )
    commands.run(argv, timeout=max(120, int(duration) + 60))


def capture_web_or_screen(
    project_id: str,
    url_or_target: str = "",
    mode: str = "screenshot",
    duration_sec: float = 3.0,
    crop_selector: str = "",
    css_selector: str = "",
    scroll_animation: str = "",
    output_name: str = "",
    fps: int = 5,
    viewport_width: int = 1440,
    viewport_height: int = 900,
) -> dict[str, Any]:
    """Capture a URL or screen target as a still or a short B-roll clip."""

    tool = "capture_web_or_screen"
    crop_selector = css_selector or crop_selector
    target_value = str(url_or_target or "").strip()
    if not target_value:
        raise InvalidArgumentError(
            "url_or_target must not be empty", details={"argument": "url_or_target"}
        )
    selected = str(mode or "").strip().lower()
    if selected == "video_clip":
        selected = "clip"
    if selected not in {"screenshot", "clip"}:
        raise InvalidArgumentError(
            "mode must be 'screenshot', 'clip', or 'video_clip'",
            details={"argument": "mode", "value": mode},
        )
    try:
        duration = float(duration_sec)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "duration_sec must be a number",
            details={"argument": "duration_sec", "value": duration_sec},
        ) from exc
    if not 0.1 <= duration <= 120.0:
        raise InvalidArgumentError(
            "duration_sec must be between 0.1 and 120",
            details={"argument": "duration_sec", "value": duration_sec},
        )
    if not 1 <= fps <= 30:
        raise InvalidArgumentError(
            "fps must be between 1 and 30",
            details={"argument": "fps", "value": fps},
        )
    for name, value in (("viewport_width", viewport_width), ("viewport_height", viewport_height)):
        if not 320 <= value <= 3840:
            raise InvalidArgumentError(
                f"{name} must be between 320 and 3840",
                details={"argument": name, "value": value},
            )
    screen_target = _is_screen_target(target_value)
    browser = "" if screen_target else _chrome()
    stem = _slug(Path(output_name).stem or Path(url_or_target).stem or "capture")
    extension = ".mp4" if selected == "clip" else ".png"
    kind = "broll" if selected == "clip" else "images"
    relative = f"assets/{kind}/{stem}{extension}"
    key = storage.cache_key(
        tool,
        url_or_target,
        selected,
        duration if selected == "clip" else 0,
        crop_selector,
        scroll_animation,
        fps if selected == "clip" else 0,
        viewport_width,
        viewport_height,
    )
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")
    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    crop = _crop_filter(crop_selector, viewport_width, viewport_height)

    if screen_target:
        raw = target.with_name(f".{target.stem}.raw{extension}")
        try:
            _capture_screen(
                target=raw,
                mode=selected,
                duration=duration,
                fps=fps,
                width=viewport_width,
                height=viewport_height,
            )
            _require_output(raw)
            if crop and selected == "screenshot":
                commands.run(
                    [
                        _ffmpeg(),
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(raw),
                        "-vf",
                        crop,
                        str(target),
                    ]
                )
                raw.unlink(missing_ok=True)
            else:
                raw.replace(target)
        finally:
            raw.unlink(missing_ok=True)
    elif selected == "screenshot":
        raw = target.with_name(f".{target.stem}.raw.png")
        css_crop = crop_selector if _is_css_selector(crop_selector) else ""
        if scroll_animation or css_crop:
            with _cdp_scroll_capture(
                url_or_target,
                width=viewport_width,
                height=viewport_height,
                selector=crop_selector if scroll_animation else "",
                scroll_animation=scroll_animation,
                clip_selector=css_crop,
            ) as capture:
                raw.write_bytes(capture(1.0))
            _require_output(raw)
            if crop:
                commands.run(
                    [
                        _ffmpeg(),
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(raw),
                        "-vf",
                        crop,
                        str(target),
                    ]
                )
            else:
                raw.replace(target)
            raw.unlink(missing_ok=True)
            _require_output(target)
            record = storage.write_output(
                project_id,
                relative,
                source_path=target,
                kind=kind,
                license="source",
                source=f"chromium:{Path(url_or_target).name or url_or_target}",
                cache_key=key,
                metadata={"scroll_animation": scroll_animation, "selector": crop_selector},
            )
            return _payload(tool, project_id, record, mode="local")
        argv = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--window-size={viewport_width},{viewport_height}",
            f"--screenshot={raw}",
            url_or_target,
        ]
        try:
            commands.run(argv, timeout=120)
            _require_output(raw)
            if crop:
                commands.run(
                    [
                        _ffmpeg(),
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(raw),
                        "-vf",
                        crop,
                        str(target),
                    ]
                )
            else:
                raw.replace(target)
        finally:
            raw.unlink(missing_ok=True)
    else:
        total = max(1, round(duration * fps))
        css_crop = crop_selector if _is_css_selector(crop_selector) else ""
        if scroll_animation or css_crop:
            with tempfile.TemporaryDirectory(prefix="vf-capture-") as raw_dir:
                frames = Path(raw_dir) / "frames"
                frames.mkdir(parents=True)
                with _cdp_scroll_capture(
                    url_or_target,
                    width=viewport_width,
                    height=viewport_height,
                    selector=crop_selector if scroll_animation else "",
                    scroll_animation=scroll_animation,
                    clip_selector=css_crop,
                ) as capture:
                    for index in range(total):
                        progress = index / max(1, total - 1)
                        frame = frames / f"frame-{index:05d}.png"
                        frame.write_bytes(capture(progress))
                if crop:
                    for frame in frames.glob("frame-*.png"):
                        commands.run(
                            [
                                _ffmpeg(),
                                "-hide_banner",
                                "-loglevel",
                                "error",
                                "-y",
                                "-i",
                                str(frame),
                                "-vf",
                                crop,
                                str(frame.with_suffix(".crop.png")),
                            ]
                        )
                        frame.with_suffix(".crop.png").replace(frame)
                _encode_frames(frames, target, fps=fps, duration=duration, alpha=False)
        else:
            with tempfile.TemporaryDirectory(prefix="vf-capture-") as raw_dir:
                frames = Path(raw_dir) / "frames"
                frames.mkdir(parents=True)
                for index in range(total):
                    moment = index / fps
                    frame = frames / f"frame-{index:05d}.png"
                    argv = [
                        browser,
                        "--headless=new",
                        "--disable-gpu",
                        "--hide-scrollbars",
                        f"--window-size={viewport_width},{viewport_height}",
                        f"--virtual-time-budget={max(500, round(moment * 1000))}",
                        f"--screenshot={frame}",
                        f"{url_or_target}{'&' if '?' in url_or_target else '?'}vf_time={moment:.4f}"
                        + (f"&vf_scroll={scroll_animation}" if scroll_animation else ""),
                    ]
                    commands.run(argv, timeout=15)
                    if not frame.is_file():
                        raise OutputNotProducedError(
                            f"Chromium did not capture frame {index}",
                            details={"path": str(frame)},
                        )
                if crop:
                    for frame in frames.glob("frame-*.png"):
                        commands.run(
                            [
                                _ffmpeg(),
                                "-hide_banner",
                                "-loglevel",
                                "error",
                                "-y",
                                "-i",
                                str(frame),
                                "-vf",
                                crop,
                                str(frame.with_suffix(".crop.png")),
                            ]
                        )
                        frame.with_suffix(".crop.png").replace(frame)
                _encode_frames(frames, target, fps=fps, duration=duration, alpha=False)
    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind=kind,
        license="source",
        source=(
            f"screen:{os.environ.get('DISPLAY', '')}"
            if screen_target
            else f"chromium:{Path(url_or_target).name or url_or_target}"
        ),
        cache_key=key,
        metadata={
            "mode": selected,
            "url_or_target": url_or_target,
            "crop_selector": crop_selector,
            "crop_filter": crop,
            "duration_sec": duration if selected == "clip" else 0,
            "fps": fps if selected == "clip" else 0,
            "viewport": [viewport_width, viewport_height],
        },
    )
    return _payload(tool, project_id, record, mode="local")


def _is_css_selector(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    if raw.startswith(("#", ".", "[", "*", ":")):
        return True
    return bool(re.search(r"[>\s]", raw)) or bool(re.search(r"[A-Za-z]", raw))


def _crop_filter(selector: str, width: int, height: int) -> str:
    """Interpret ``x,y,w,h`` as a crop; keep CSS selectors in metadata."""

    raw = str(selector or "").strip()
    if not raw:
        return ""
    parts = [part for part in re.split(r"[x,\s]+", raw) if part]
    if len(parts) == 4:
        try:
            x, y, w, h = (int(part) for part in parts)
        except ValueError:
            return ""
        if w > 0 and h > 0:
            return f"crop={min(w, width)}:{min(h, height)}:{max(0, x)}:{max(0, y)}"
    return ""


def image_to_broll_motion(
    project_id: str,
    image_path: str,
    duration_sec: float = 4.0,
    motion: str = "zoom_in",
    aspect_ratio: str = "",
    width: int = 0,
    height: int = 0,
) -> dict[str, Any]:
    """Animate a still image into a zoom or pan B-roll clip with FFmpeg."""

    tool = "image_to_broll_motion"
    source = _ensure_input(image_path, "image_path")
    try:
        duration = float(duration_sec)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            "duration_sec must be a number",
            details={"argument": "duration_sec", "value": duration_sec},
        ) from exc
    if not 0.1 <= duration <= 120.0:
        raise InvalidArgumentError(
            "duration_sec must be between 0.1 and 120",
            details={"argument": "duration_sec", "value": duration_sec},
        )
    if motion not in MOTIONS:
        raise InvalidArgumentError(
            f"motion must be one of: {', '.join(sorted(MOTIONS))}",
            details={"argument": "motion", "value": motion},
        )

    width, height = _broll_dimensions(project_id, aspect_ratio, width, height)
    key = storage.cache_key(
        tool,
        storage.file_fingerprint(source),
        duration,
        motion,
        width,
        height,
    )
    suffix = "" if (width, height) == (1080, 1920) else f"_{width}x{height}"
    relative = f"assets/broll/{source.stem}_{motion}{suffix}.mp4"
    cached = storage.cached_asset(project_id, relative, key)
    if cached is not None:
        return _payload(tool, project_id, cached, mode="cache")
    ffmpeg = _ffmpeg()
    target = storage.asset_path(project_id, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    filter_chain = build_broll_filter(
        motion=motion,
        duration=duration,
        width=width,
        height=height,
    )
    commands.run(
        [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-vf",
            filter_chain,
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(target),
        ]
    )
    _require_output(target)
    record = storage.write_output(
        project_id,
        relative,
        source_path=target,
        kind="broll",
        license="source",
        source="ffmpeg:broll",
        cache_key=key,
        metadata={
            "motion": motion,
            "duration_sec": duration,
            "width": width,
            "height": height,
            "aspect_ratio": aspect_ratio or (
                f"{width}:{height}" if width != height else "1:1"
            ),
            "input": str(source),
        },
    )
    return _payload(tool, project_id, record, mode="local")


def build_broll_filter(
    *,
    motion: str,
    duration: float,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> str:
    """Build the FFmpeg zoompan chain used for still-image B-roll."""

    if motion not in MOTIONS:
        raise InvalidArgumentError(
            f"motion must be one of: {', '.join(sorted(MOTIONS))}",
            details={"argument": "motion", "value": motion},
        )
    frames = max(1, int(round(duration * fps)))
    pre = (
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
        f"crop={width * 2}:{height * 2}"
    )
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    if motion == "zoom_in":
        zoom, x_expr, y_expr = "min(zoom+0.0020,1.25)", center_x, center_y
    elif motion == "zoom_out":
        zoom, x_expr, y_expr = "if(eq(on,1),1.25,max(zoom-0.0020,1.0))", center_x, center_y
    elif motion == "pan_left":
        zoom, x_expr, y_expr = "1.15", f"(iw-iw/zoom)*(1-on/{frames})", center_y
    else:
        zoom, x_expr, y_expr = "1.15", f"(iw-iw/zoom)*on/{frames}", center_y
    zoompan = f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps={fps}"
    return f"{pre},{zoompan},format=yuv420p"


def segments_to_srt(segments: Sequence[dict[str, Any]]) -> str:
    """Render normalized segments as SubRip."""

    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        start = _srt_time(float(segment.get("start", 0.0)))
        end = _srt_time(float(segment.get("end", segment.get("start", 0.0))))
        text = str(segment.get("text", "")).strip() or " "
        blocks.append(f"{index}\n{start} --> {end}\n{text}\n")
    return "\n".join(blocks)


def segments_to_ass(
    segments: Sequence[dict[str, Any]],
    *,
    style: str = "shorts_karaoke",
) -> str:
    """Render normalized segments as an ASS subtitle file."""

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Karaoke,Arial,72,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,4,2,2,60,60,180,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines: list[str] = []
    for segment in segments:
        start = _ass_time(float(segment.get("start", 0.0)))
        end = _ass_time(float(segment.get("end", segment.get("start", 0.0))))
        text = _ass_escape(str(segment.get("text", "")))
        lines.append(f"Dialogue: 0,{start},{end},Karaoke,,0,0,0,,{text}")
    return header + "\n".join(lines) + ("\n" if lines else "")


def _transcribe_with_whisper(binary: str, audio: Path, language: str) -> list[dict[str, Any]]:
    model = os.environ.get("VF_WHISPER_MODEL")
    if not model:
        raise MissingCommandError(
            "VF_WHISPER_MODEL must point at a whisper.cpp model",
            details={"env": ["VF_WHISPER_MODEL"], "capability": "asr"},
        )
    model_path = _ensure_input(model, "VF_WHISPER_MODEL")
    with tempfile.TemporaryDirectory(prefix="vf-whisper-") as raw:
        output_base = Path(raw) / "transcript"
        commands.run(
            [
                binary,
                "-m",
                str(model_path),
                "-f",
                str(audio),
                "-l",
                language,
                "-oj",
                "-of",
                str(output_base),
                "-np",
            ]
        )
        candidates = [Path(f"{output_base}.json"), output_base.with_suffix(".json")]
        json_path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if json_path is None:
            raise OutputNotProducedError(
                "whisper.cpp did not produce its JSON transcript",
                details={"output_base": str(output_base)},
            )
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    return _parse_transcript_payload(payload)


def _transcribe_with_stable_whisper(audio: Path, language: str) -> list[dict[str, Any]]:
    import stable_whisper

    model_name = os.environ.get("VF_STABLE_TS_MODEL", "base")
    model = stable_whisper.load_model(model_name)
    result = model.transcribe(str(audio), language=language, word_timestamps=True)
    payload = result.to_dict() if hasattr(result, "to_dict") else result
    return _parse_transcript_payload(payload)


def _stable_whisper_available() -> bool:
    return importlib.util.find_spec("stable_whisper") is not None


def _transcribe_remote(source: Path, language: str) -> list[dict[str, Any]]:
    """Run ASR on the GPU worker and parse its JSON artifact."""

    result = ROUTER.submit(
        "asr",
        {
            "input": str(source),
            "language": language,
            "model": os.environ.get("VF_WHISPER_MODEL", "large-v3"),
            "output_name": "transcript.json",
        },
    )
    text = ""
    if isinstance(result, dict) and result.get("data") is not None:
        raw = result["data"]
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    else:
        path = _path_from_value(result)
        if path is not None and path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise RemoteResultError(
            "remote asr returned no transcript payload",
            details={"capability": "asr"},
        )
    segments = _parse_transcript_payload(json.loads(text))
    if not segments:
        raise RemoteResultError(
            "remote asr returned an empty transcript",
            details={"capability": "asr"},
        )
    return segments


def _parse_transcript_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw_segments = payload.get("transcription")
    if raw_segments is None:
        raw_segments = payload.get("segments")
    segments: list[dict[str, Any]] = []
    for item in raw_segments or []:
        if not isinstance(item, dict):
            continue
        start, end = _segment_bounds(item)
        words: list[dict[str, Any]] = []
        for key in ("words", "tokens"):
            for token in item.get(key) or []:
                if not isinstance(token, dict):
                    continue
                word = str(token.get("word") or token.get("text") or "").strip()
                if not word:
                    continue
                word_start, word_end = _segment_bounds(token)
                words.append({"word": word, "start": word_start, "end": word_end})
            if words:
                break
        segments.append(
            {
                "start": start,
                "end": end,
                "text": str(item.get("text", "")).strip(),
                "words": words,
            }
        )
    return segments


def _segment_bounds(item: dict[str, Any]) -> tuple[float, float]:
    offsets = item.get("offsets")
    if isinstance(offsets, dict):
        start = float(offsets.get("from", 0.0)) / 1000.0
        end = float(offsets.get("to", offsets.get("from", 0.0))) / 1000.0
        return start, end
    return float(item.get("start", 0.0)), float(item.get("end", item.get("start", 0.0)))


def _matte_video(source: Path, target: Path) -> None:
    ffmpeg = _ffmpeg()
    fps = os.environ.get("VF_MATTE_FPS", "30")
    _validate_fps(fps)
    with tempfile.TemporaryDirectory(prefix="vf-matte-") as raw:
        workdir = Path(raw)
        frames = workdir / "frames"
        mattes = workdir / "matte"
        frames.mkdir()
        mattes.mkdir()
        commands.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-vf",
                f"fps={fps}",
                str(frames / "%06d.png"),
            ]
        )
        extracted = sorted(frames.glob("*.png"))
        if not extracted:
            raise OutputNotProducedError(
                "FFmpeg extracted no frames for background removal",
                details={"input": str(source)},
            )
        for index, frame in enumerate(extracted, start=1):
            _run_rembg(frame, mattes / f"{index:06d}.png")
        commands.run(
            [
                ffmpeg,
                "-y",
                "-framerate",
                fps,
                "-i",
                str(mattes / "%06d.png"),
                "-c:v",
                "libvpx-vp9",
                "-pix_fmt",
                "yuva420p",
                "-b:v",
                "0",
                "-crf",
                "30",
                str(target),
            ]
        )


def _run_rembg(source: Path, target: Path) -> None:
    template = os.environ.get("VF_REMBG_CMD")
    if template:
        commands.run(
            commands.expand_template(
                template,
                {"input": str(source), "output": str(target)},
                name="rembg command",
            )
        )
        return
    binary = shutil.which("rembg")
    if binary:
        commands.run([binary, "i", str(source), str(target)])
        return
    if importlib.util.find_spec("rembg") is not None:
        commands.run([sys.executable, "-m", "rembg", "i", str(source), str(target)])
        return
    raise MissingCommandError(
        "rembg is not installed; set VF_REMBG_CMD or install rembg",
        details={"env": ["VF_REMBG_CMD"], "capability": "matte"},
    )


def _materialize_remote(
    *,
    project_id: str,
    relative_path: str,
    result: Any,
    capability: str,
    cache_key: str,
    kind: str,
) -> storage.AssetRecord:
    metadata: dict[str, Any] = {"capability": capability, "mode": "remote"}
    if isinstance(result, dict) and isinstance(result.get("metadata"), dict):
        metadata.update(result["metadata"])

    data: bytes | None = None
    if isinstance(result, dict) and result.get("data") is not None:
        raw = result["data"]
        data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    elif isinstance(result, (bytes, bytearray)):
        data = bytes(result)

    if data is not None:
        return storage.write_output(
            project_id,
            relative_path,
            data=data,
            kind=kind,
            license="generated",
            source=f"remote:{capability}",
            cache_key=cache_key,
            metadata=metadata,
            ai_generated=True,
        )

    source = _path_from_value(result)
    if source is None or not source.is_file():
        raise RemoteResultError(
            f"remote {capability!r} result has no readable file",
            details={"capability": capability, "result_type": type(result).__name__},
        )
    return storage.write_output(
        project_id,
        relative_path,
        source_path=source,
        kind=kind,
        license="generated",
        source=f"remote:{capability}",
        cache_key=cache_key,
        metadata=metadata,
        ai_generated=True,
    )


def _path_from_value(value: Any) -> Path | None:
    if isinstance(value, (str, Path)):
        return Path(str(value)).expanduser()
    if isinstance(value, dict):
        for key in ("path", "output", "asset_path", "file"):
            if value.get(key):
                return Path(str(value[key])).expanduser()
        return None
    for attribute in ("path", "output", "file"):
        raw = getattr(value, attribute, None)
        if raw:
            return Path(str(raw)).expanduser()
    return None


def _parse_props(props_json: Any) -> dict[str, Any]:
    if isinstance(props_json, dict):
        return dict(props_json)
    if props_json is None or props_json == "":
        return {}
    if not isinstance(props_json, str):
        raise InvalidArgumentError(
            "props_json must be a JSON object string",
            details={"argument": "props_json"},
        )
    try:
        parsed = json.loads(props_json)
    except json.JSONDecodeError as exc:
        raise InvalidArgumentError(
            f"props_json is not valid JSON: {exc.msg}",
            details={"argument": "props_json", "line": exc.lineno, "column": exc.colno},
        ) from exc
    if not isinstance(parsed, dict):
        raise InvalidArgumentError(
            "props_json must decode to an object",
            details={"argument": "props_json"},
        )
    return parsed


def _project_canvas(project_id: str) -> tuple[int, int] | None:
    path = storage.project_dir(project_id) / "project_state.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    media = payload.get("media_info") if isinstance(payload, dict) else None
    if not isinstance(media, dict):
        return None
    try:
        width = int(media.get("width") or 0)
        height = int(media.get("height") or 0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _graphic_dimensions(project_id: str, width: int, height: int) -> tuple[int, int]:
    project = _project_canvas(project_id)
    if width and not height and project:
        height = round(width * project[1] / max(1, project[0]))
    elif height and not width and project:
        width = round(height * project[0] / max(1, project[1]))
    if not width and not height:
        width, height = project or (1920, 1080)
    width = max(2, int(width) // 2 * 2)
    height = max(2, int(height) // 2 * 2)
    return width, height


def _broll_dimensions(
    project_id: str,
    aspect_ratio: str,
    width: int,
    height: int,
) -> tuple[int, int]:
    explicit_aspect = str(aspect_ratio or "").strip()
    if explicit_aspect and explicit_aspect not in BROLL_ASPECTS:
        raise InvalidArgumentError(
            f"aspect_ratio must be one of: {', '.join(sorted(BROLL_ASPECTS))}",
            details={"argument": "aspect_ratio", "value": aspect_ratio},
        )
    if width or height:
        if not width or not height:
            raise InvalidArgumentError(
                "width and height must be passed together",
                details={"argument": "width", "value": width},
            )
        resolved = (int(width), int(height))
    elif explicit_aspect:
        resolved = BROLL_ASPECTS[explicit_aspect]
    else:
        resolved = _project_canvas(project_id) or _broll_size()
    for name, value in (("width", resolved[0]), ("height", resolved[1])):
        if value <= 0 or value % 2:
            raise InvalidArgumentError(
                f"{name} must be a positive even number",
                details={"argument": name, "value": value},
            )
    return resolved


def _broll_size() -> tuple[int, int]:
    raw = os.environ.get("VF_BROLL_SIZE", "1080x1920")
    try:
        width_text, height_text = raw.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            f"VF_BROLL_SIZE must look like WIDTHxHEIGHT, got {raw!r}",
            details={"env": "VF_BROLL_SIZE", "value": raw},
        ) from exc
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise InvalidArgumentError(
            f"VF_BROLL_SIZE must use positive even dimensions, got {raw!r}",
            details={"env": "VF_BROLL_SIZE", "value": raw},
        )
    return width, height


def _validate_fps(value: str) -> None:
    try:
        fps = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError(
            f"VF_MATTE_FPS must be a number, got {value!r}",
            details={"env": "VF_MATTE_FPS", "value": value},
        ) from exc
    if not 1.0 <= fps <= 240.0:
        raise InvalidArgumentError(
            f"VF_MATTE_FPS must be between 1 and 240, got {value!r}",
            details={"env": "VF_MATTE_FPS", "value": value},
        )


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def _srt_time(seconds: float) -> str:
    total = max(0, int(round(seconds * 1000.0)))
    milliseconds = total % 1000
    total //= 1000
    minute_total, second = divmod(total, 60)
    hour, minute = divmod(minute_total, 60)
    return f"{hour:02d}:{minute:02d}:{second:02d},{milliseconds:03d}"


def _ass_time(seconds: float) -> str:
    total = max(0, int(round(seconds * 100.0)))
    centiseconds = total % 100
    total //= 100
    minute_total, second = divmod(total, 60)
    hour, minute = divmod(minute_total, 60)
    return f"{hour}:{minute:02d}:{second:02d}.{centiseconds:02d}"


def _payload(
    tool: str,
    project_id: str,
    record: storage.AssetRecord,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "tool": tool,
        "project_id": project_id,
        "output": str(record.path),
        "relative_path": record.relative_path,
        "cache_key": record.cache_key,
        "cached": record.cached,
        "sidecar": str(record.sidecar),
        "license": record.license,
        "source": record.source,
        "sha256": record.sha256,
    }
    payload.update(extra)
    return payload


def _assets_payload(
    tool: str,
    project_id: str,
    records: Sequence[storage.AssetRecord],
    *,
    mode: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "tool": tool,
        "project_id": project_id,
        "mode": mode,
        "cached": all(record.cached for record in records),
        "assets": [_payload(tool, project_id, record, mode=mode) for record in records],
    }


def _ensure_input(value: str | Path | None, argument: str) -> Path:
    if value is None or str(value) == "":
        raise InvalidArgumentError(f"{argument} is required", details={"argument": argument})
    resolved = Path(value).expanduser()
    if not resolved.is_file():
        raise InputNotFoundError(
            f"{argument} not found: {resolved}",
            details={"argument": argument, "path": str(resolved)},
        )
    return resolved


def _require_output(path: Path) -> None:
    if not path.is_file():
        raise OutputNotProducedError(
            f"command did not produce {path}",
            details={"path": str(path)},
        )


def _ffmpeg() -> str:
    configured = os.environ.get("VF_FFMPEG")
    if configured:
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise MissingCommandError(
        "ffmpeg is required for this tool; install it or set VF_FFMPEG",
        details={"env": ["VF_FFMPEG"], "executable": "ffmpeg"},
    )


def _slug(value: str, *, limit: int = 40) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value.lower())
    collapsed = "_".join(part for part in cleaned.split("_") if part)
    return (collapsed or "asset")[:limit]
