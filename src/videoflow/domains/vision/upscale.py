"""Image and video upscale through remote compute, Real-ESRGAN or FFmpeg."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from . import commands, common, storage
from .common import (
    VIDEO_EXTENSIONS,
    _ensure_input,
    _ffmpeg,
    _materialize_remote,
    _payload,
    _probe_stream,
    _require_output,
)
from .errors import InvalidArgumentError

UPSCALE_MAX_DIM = 8192


def _select_upscale_backend(requested: str) -> tuple[str, str]:
    selected = (requested or "auto").strip().lower()
    if selected not in {"auto", "remote", "realesrgan", "realesrgan_cmd", "ffmpeg"}:
        raise InvalidArgumentError(
            "backend must be auto, remote, realesrgan, realesrgan_cmd, or ffmpeg",
            details={"argument": "backend", "value": requested},
        )
    if selected == "auto":
        if common.ROUTER.health("upscale"):
            return "remote", ""
        if os.environ.get("VF_REALESRGAN_CMD"):
            return "realesrgan_cmd", ""
        if shutil.which("realesrgan-ncnn-vulkan"):
            return "realesrgan", ""
        return "ffmpeg", "no upscale backend is installed; using FFmpeg lanczos"
    if selected == "remote":
        if common.ROUTER.health("upscale"):
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
            result = common.ROUTER.submit(
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
