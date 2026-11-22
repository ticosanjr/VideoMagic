"""Capture a URL or the local screen as a screenshot or B-roll clip."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from . import commands, storage
from .browser import _chrome
from .cdp_frames import _cdp_frame_capture
from .cdp_scroll import _cdp_scroll_capture
from .common import (
    _crop_filter,
    _ffmpeg,
    _is_css_selector,
    _is_screen_target,
    _payload,
    _require_output,
    _slug,
)
from .errors import InvalidArgumentError, MissingCommandError
from .graphics_web import _encode_frames


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
    viewport_width = max(2, int(viewport_width) // 2 * 2)
    viewport_height = max(2, int(viewport_height) // 2 * 2)
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
                    for frame in sorted(frames.glob("frame-0*.*")):
                        if ".crop." in frame.name:
                            continue
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
                _encode_frames(
                    frames,
                    target,
                    fps=fps,
                    duration=duration,
                    alpha=False,
                    extension="png",
                )
        else:
            with tempfile.TemporaryDirectory(prefix="vf-capture-") as raw_dir:
                frames = Path(raw_dir) / "frames"
                frames.mkdir(parents=True)
                with _cdp_frame_capture(
                    url_or_target,
                    width=viewport_width,
                    height=viewport_height,
                    alpha=False,
                    jpeg=True,
                    timeout_sec=10.0,
                ) as capture:
                    for index in range(total):
                        moment = index / fps
                        frame = frames / f"frame-{index:05d}.jpg"
                        frame.write_bytes(capture(moment))
                if crop:
                    for frame in sorted(frames.glob("frame-0*.*")):
                        if ".crop." in frame.name:
                            continue
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
                _encode_frames(
                    frames,
                    target,
                    fps=fps,
                    duration=duration,
                    alpha=False,
                    extension="jpg",
                )
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
