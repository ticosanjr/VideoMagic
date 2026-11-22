"""Motion graphics entry point, canvas resolution and FFmpeg engine."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import commands, storage
from .common import (
    MOTION_ENGINES,
    _ffmpeg,
    _payload,
    _require_output,
    _slug,
)
from .errors import InvalidArgumentError, MissingCommandError
from .graphics_web import _render_web_graphic, _scaled_viewport


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
