"""HTML/HyperFrames graphics rendering through headless Chromium."""

from __future__ import annotations

import contextlib
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from . import commands, storage
from .browser import _chrome
from .cdp_frames import _cdp_frame_capture
from .common import (
    _assert_alpha,
    _ffmpeg,
    _payload,
    _require_output,
    _slug,
)
from .errors import InputNotFoundError, InvalidArgumentError


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
    draft: bool = False,
    extension: str = "png",
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
        str(frames / f"frame-%05d.{extension}"),
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-t",
        f"{duration:.3f}",
    ]
    if alpha:
        argv.extend(
            [
                "-c:v",
                "libvpx-vp9",
                "-pix_fmt",
                "yuva420p",
                "-auto-alt-ref",
                "0",
                "-b:v",
                "0",
                "-crf",
                "34" if draft else "24",
            ]
        )
    else:
        argv.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast" if draft else "veryfast",
                "-crf",
                "28" if draft else "18",
                "-pix_fmt",
                "yuv420p",
            ]
        )
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
    _chrome()
    entry = entry.resolve()
    viewport_width, viewport_height = _scaled_viewport(width, height, 1.0)
    device_scale = max(0.1, min(1.0, float(draft_scale)))
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
    fps = 15 if draft_scale < 1.0 else 30
    total = max(1, round(duration * fps))
    props_query = quote(json.dumps(props, separators=(",", ":")))
    with tempfile.TemporaryDirectory(prefix="vf-html-") as raw:
        frames = Path(raw) / "frames"
        frames.mkdir(parents=True)
        separator = "&" if "?" in entry.as_uri() else "?"
        url = f"{entry.as_uri()}{separator}vf_props={props_query}"
        extension = "png" if alpha else "jpg"
        with _cdp_frame_capture(
            url,
            width=viewport_width,
            height=viewport_height,
            alpha=alpha,
            scale=device_scale,
            jpeg=not alpha,
            timeout_sec=10.0,
        ) as capture:
            for index in range(total):
                moment = index / fps
                frame = frames / f"frame-{index:05d}.{extension}"
                frame.write_bytes(capture(moment))
        _encode_frames(
            frames,
            target,
            fps=fps,
            duration=duration,
            alpha=alpha,
            draft=draft_scale < 1.0,
            extension=extension,
        )
    if alpha:
        _assert_alpha(target)
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
            "viewport": [
                max(2, round(viewport_width * device_scale / 2) * 2),
                max(2, round(viewport_height * device_scale / 2) * 2),
            ],
            "source_sha256": digest,
            "props": props,
        },
    )
    return _payload(tool, project_id, record, mode="local")
