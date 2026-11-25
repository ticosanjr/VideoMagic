"""Still-image B-roll with FFmpeg zoom and pan motion."""

from __future__ import annotations

import os
from typing import Any

from ..toolkit import commands, storage
from ..toolkit.assets import (
    _ensure_input,
    _ffmpeg,
    _materialize_remote,
    _payload,
    _require_output,
)
from ..toolkit.errors import InvalidArgumentError
from . import common
from .common import BROLL_ASPECTS, MOTIONS
from .motion import _project_canvas


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
    if common.ROUTER.health("ffmpeg_transcode"):
        try:
            result = common.ROUTER.submit(
                "ffmpeg_transcode",
                {
                    "input": str(source),
                    "duration_sec": duration,
                    "filter": filter_chain,
                    "fps": 30,
                    "still": True,
                    "crf": 18,
                    "output_name": f"{source.stem}_{motion}.mp4",
                },
            )
            record = _materialize_remote(
                project_id=project_id,
                relative_path=relative,
                result=result,
                capability="ffmpeg_transcode",
                cache_key=key,
                kind="broll",
            )
            return _payload(tool, project_id, record, mode="remote")
        except Exception:  # noqa: BLE001 - local FFmpeg is the contract
            pass
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
    step = 0.06 / max(1, frames)
    if motion == "zoom_in":
        zoom, x_expr, y_expr = f"min(zoom+{step:.8f},1.06)", center_x, center_y
    elif motion == "zoom_out":
        zoom, x_expr, y_expr = (
            f"if(eq(on,1),1.06,max(zoom-{step:.8f},1.0))",
            center_x,
            center_y,
        )
    elif motion == "pan_left":
        zoom, x_expr, y_expr = "1.06", f"(iw-iw/zoom)*(1-on/{frames})", center_y
    else:
        zoom, x_expr, y_expr = "1.06", f"(iw-iw/zoom)*on/{frames}", center_y
    zoompan = f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps={fps}"
    return f"{pre},{zoompan},format=yuv420p"


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
