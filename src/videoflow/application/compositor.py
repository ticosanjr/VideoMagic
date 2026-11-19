"""High-level compositors for depth, picture-in-picture, parallax, and previews.

The compositors stay deterministic: they build overlay clips with explicit
anchors and ``z`` values and delegate the heavy visual work to the bundled
vision tools. Project state is the source of truth; every mutation goes through
``save_project_state``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from html import escape
from pathlib import Path
from typing import Any

from videoflow.application.masks import ensure_rounded_mask
from videoflow.application.projects import (
    get_project,
    load_project_state,
    save_project_state,
)
from videoflow.application.time_map import timeline_to_source_sec
from videoflow.domain.errors import ExportError
from videoflow.domain.state import OverlayClip, ProjectState
from videoflow.runtime import find_binary

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _canvas(state: ProjectState) -> tuple[int, int]:
    media = state.media_info
    if media is not None and media.width > 0 and media.height > 0:
        return _even(media.width), _even(media.height)
    return 1920, 1080


def _even(value: int) -> int:
    return max(2, int(value) // 2 * 2)


def _fps(state: ProjectState) -> float:
    media = state.media_info
    if media is None:
        return 30.0
    return max(1.0, media.fps_num / max(1, media.fps_den))


def _runtime(project_id: str) -> tuple[Any, ProjectState, Path]:
    record = get_project(project_id)
    state = load_project_state(record)
    return record, state, Path(record.output).expanduser()


def _vision_module() -> Any:
    from videoflow_mcp_vision import tools

    return tools


def _vision_call(name: str, func: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        payload = func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - normalize domain server failures
        raise ExportError(f"{name} failed: {exc}") from exc
    if not isinstance(payload, dict) or not payload.get("output"):
        raise ExportError(f"{name} did not return an output path")
    return payload


def _remove_background(
    project_id: str,
    path: Path,
    *,
    is_video: bool,
) -> dict[str, Any]:
    tools = _vision_module()
    return _vision_call(
        "remove_background",
        tools.remove_background,
        project_id,
        str(path),
        is_video=is_video,
    )


def _render_graphic(
    project_id: str,
    *,
    template_or_code: str,
    props: dict[str, Any],
    duration: float,
    alpha: bool,
    width: int,
    height: int,
    draft: bool = False,
) -> dict[str, Any]:
    tools = _vision_module()
    return _vision_call(
        "render_motion_graphic",
        tools.render_motion_graphic,
        project_id,
        engine="hyperframes",
        template_or_code=template_or_code,
        props_json=json.dumps(props, ensure_ascii=False),
        duration_sec=duration,
        alpha=alpha,
        draft=draft,
        width=width,
        height=height,
    )


def _run_ffmpeg(command: list[str], *, what: str) -> None:
    binary = find_binary(command[0])
    if binary is None:
        raise ExportError(f"{command[0]} is required for {what}")
    completed = subprocess.run(
        [binary, *command[1:]],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        tail = completed.stderr.strip().splitlines()
        error = ExportError(
            f"{what} failed: " + (tail[-1] if tail else "unknown error")
        )
        error.command = " ".join([binary, *command[1:]])
        error.stderr = completed.stderr
        raise error


def _cache_path(directory: Path, stem: str, *parts: Any) -> Path:
    digest = hashlib.sha256(
        json.dumps(parts, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return directory / f"{stem}_{digest}"


def _trim_clip(
    project_id: str,
    state: ProjectState,
    start_sec: float,
    end_sec: float,
) -> Path:
    """Cut only the requested range from the primary source."""

    media = state.media_info
    if media is None or not media.source_path:
        raise ExportError("Project has no media")
    source = Path(media.source_path).expanduser()
    if not source.is_file():
        raise ExportError(f"Source media is offline: {source}")
    duration = end_sec - start_sec
    if duration <= 0.05:
        raise ExportError("end_sec must be at least 50 ms after start_sec")
    try:
        source_start = timeline_to_source_sec(state, start_sec)
    except ValueError:
        source_start = max(0.0, start_sec)
    record = get_project(project_id)
    work = Path(record.output) / "work" / "compositor"
    work.mkdir(parents=True, exist_ok=True)
    target = _cache_path(
        work,
        f"{source.stem}_clip",
        str(source.resolve()),
        source.stat().st_mtime_ns,
        round(source_start, 4),
        round(duration, 4),
    ).with_suffix(".mp4")
    if target.is_file():
        return target
    _run_ffmpeg(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{source_start:.4f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.4f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(target),
        ],
        what="depth composite trim",
    )
    return target


def _next_overlay_id(overlays: list[OverlayClip]) -> str:
    used = {overlay.overlay_id for overlay in overlays}
    index = len(overlays) + 1
    while f"overlay-{index}" in used:
        index += 1
    return f"overlay-{index}"


def _append_overlays(
    project_id: str,
    items: list[dict[str, Any]],
    *,
    reason: str,
) -> list[OverlayClip]:
    record = get_project(project_id)
    state = load_project_state(record)
    media = state.media_info
    if media is None:
        raise ExportError("Project has no media")
    fps = _fps(state)
    overlays = list(state.overlays)
    created: list[OverlayClip] = []
    for item in items:
        start = max(0.0, float(item["start_sec"]))
        duration = max(0.1, float(item["end_sec"]) - start)
        path = Path(str(item["path"])).expanduser()
        if not path.is_file():
            raise ExportError(f"Compositor asset does not exist: {path}")
        suffix = path.suffix.casefold()
        overlay = OverlayClip(
            overlay_id=_next_overlay_id(overlays),
            path=str(path),
            start_frame=max(0, round(start * fps)),
            duration_frames=max(1, round(duration * fps)),
            anchor=str(item.get("anchor") or "center"),  # type: ignore[arg-type]
            margin_x=max(0, int(item.get("margin_x") or 0)),
            margin_y=max(0, int(item.get("margin_y") or 0)),
            width_ratio=max(0.01, min(1.0, float(item.get("width_ratio") or 0.72))),
            z=max(0, min(1000, int(item.get("z") or 10))),
            opacity=max(0.0, min(1.0, float(item.get("opacity") or 1.0))),
            kind="video" if suffix in VIDEO_SUFFIXES else "image",
            transition_in=str(item.get("transition_in") or "fade"),
            transition_out=str(item.get("transition_out") or "fade"),
            transition_frames=max(0, min(120, int(item.get("transition_frames") or 6))),
        )
        overlays.append(overlay)
        created.append(overlay)
    save_project_state(
        record,
        state.model_copy(update={"overlays": overlays}),
        bump_revision=True,
        snapshot=True,
        snapshot_reason=reason,
        snapshot_step=reason,
    )
    return created


def _graphic_html(
    *,
    title: str,
    width: int,
    height: int,
    palette: list[str],
    font: str,
    duration: float,
) -> str:
    background = palette[0] if palette else "#101114"
    accent = palette[1] if len(palette) > 1 else "#ffcc4d"
    text = palette[2] if len(palette) > 2 else "#ffffff"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<style>
html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden;background:transparent}}
.stage{{position:relative;width:100%;height:100%;display:flex;align-items:center;
justify-content:center;font-family:"{font}",sans-serif;color:{text}}}
.card{{padding:{max(24, height // 24)}px {max(32, width // 20)}px;border-radius:28px;
background:linear-gradient(135deg,{background}f2,{background}e6);
box-shadow:0 30px 80px #0008;opacity:0;transform:translateY(36px) scale(.96);
animation:rise .8s cubic-bezier(.2,.8,.2,1) forwards}}
.eyebrow{{display:inline-block;padding:6px 14px;border-radius:999px;background:{accent};
color:#101114;font-size:{max(14, height // 90)}px;font-weight:800;letter-spacing:.14em;
text-transform:uppercase;margin-bottom:{max(14, height // 60)}px}}
h1{{margin:0;font-size:{max(36, min(height // 9, width // 9))}px;line-height:1.05;
letter-spacing:-.03em;max-width:{int(width * .8)}px}}
.rule{{width:{int(width * .12)}px;height:{max(6, height // 120)}px;background:{accent};
margin-top:{max(18, height // 40)}px;animation:grow .9s .25s ease forwards;
transform-origin:left;transform:scaleX(0)}}
@keyframes rise{{to{{opacity:1;transform:translateY(0) scale(1)}}}}
@keyframes grow{{to{{transform:scaleX(1)}}}}
</style></head>
<body><div class="stage"><div class="card"><span class="eyebrow">Depth</span>
<h1>{escape(title)}</h1><div class="rule"></div></div></div></body></html>
"""


def _parallax_html(
    *,
    image_path: Path,
    subject_path: Path,
    width: int,
    height: int,
    duration: float,
    bg_scale: float,
    fg_scale: float,
    rotate_y: float,
) -> str:
    background = image_path.resolve().as_uri()
    subject = subject_path.resolve().as_uri()
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<style>
html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden;background:#050608}}
.stage{{position:relative;width:100%;height:100%;overflow:hidden;perspective:1200px}}
.bg{{position:absolute;inset:-6%;background-image:url('{background}');background-size:cover;
background-position:center;filter:blur(6px) brightness(.62);
animation:bg {duration}s ease-in-out forwards}}
.fg{{position:absolute;inset:0;background-image:url('{subject}');background-size:contain;
background-repeat:no-repeat;background-position:center bottom;transform-origin:50% 70%;
animation:fg {duration}s ease-in-out forwards;filter:drop-shadow(0 24px 42px #0009)}}
.vignette{{position:absolute;inset:0;
background:radial-gradient(circle at 50% 45%,transparent 40%,#0009 100%)}}
@keyframes bg{{from{{transform:scale(1)}}to{{transform:scale({bg_scale:.4f})}}}}
@keyframes fg{{from{{transform:scale(1) rotateY(0deg) translateX(0)}}
to{{transform:scale({fg_scale:.4f}) rotateY({rotate_y:.2f}deg) translateX(-2%)}}}}
</style></head>
<body><div class="stage"><div class="bg"></div><div class="fg"></div>
<div class="vignette"></div></div></body></html>
"""


def _style_html(
    *,
    style_name: str,
    style_id: str,
    layout: str,
    caption: str,
    width: int,
    height: int,
    palette: list[str],
    font: str,
    duration: float,
    background_image: Path | None = None,
) -> str:
    background = palette[0] if palette else "#101114"
    accent = palette[1] if len(palette) > 1 else "#ffcc4d"
    text = palette[2] if len(palette) > 2 else "#ffffff"
    if background_image is not None:
        scene = (
            f"background-image:linear-gradient(180deg,{background}55,{background}e6),"
            f"url('{background_image.resolve().as_uri()}');"
            "background-size:cover;background-position:center;background-blend-mode:multiply"
        )
    else:
        scene = (
            f"background:radial-gradient(circle at 50% 25%,{accent}22,transparent 55%),"
            f"{background}"
        )
    words = "".join(
        f'<span style="animation-delay:{0.35 + index * 0.08:.2f}s">{escape(word)}</span> '
        for index, word in enumerate(caption.split())
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<style>
html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden;
background:{background};font-family:"{font}",sans-serif;color:{text}}}
.stage{{position:relative;width:100%;height:100%;display:flex;flex-direction:column;
justify-content:flex-end;padding:{max(24, height // 22)}px;box-sizing:border-box;
{scene}}}
.badge{{position:absolute;top:{max(24, height // 22)}px;left:{max(24, width // 22)}px;
padding:8px 16px;border-radius:999px;background:{accent};color:#101114;
font-weight:800;letter-spacing:.12em;text-transform:uppercase;font-size:{max(14, height // 96)}px}}
h1{{margin:0 0 {max(20, height // 40)}px;font-size:{max(40, min(height // 10, width // 10))}px;
line-height:1.03;letter-spacing:-.035em;max-width:{int(width * .92)}px}}
.caption{{display:flex;flex-wrap:wrap;gap:.24em;
font-size:{max(28, min(height // 16, width // 16))}px;
font-weight:800;text-transform:uppercase;line-height:1.08}}
.caption span{{opacity:0;transform:translateY(.35em);animation:word .32s ease forwards;
background:{accent};color:#101114;padding:.06em .18em;border-radius:.18em}}
.meta{{margin-top:{max(18, height // 38)}px;font-size:{max(14, height // 105)}px;
letter-spacing:.16em;text-transform:uppercase;opacity:.8}}
@keyframes word{{to{{opacity:1;transform:translateY(0)}}}}
</style></head>
<body><div class="stage"><div class="badge">{escape(layout or "style")}</div>
<h1>{escape(style_name)}</h1>
<div class="caption">{words}</div>
<div class="meta">{escape(style_id)} · {duration:.1f}s preview</div>
</div></body></html>
"""


def depth_composite(
    project_id: str,
    text_or_asset: str,
    start_sec: float,
    end_sec: float,
    *,
    style_props: dict[str, Any] | None = None,
    anchor: str = "center",
    width_ratio: float = 0.82,
) -> dict[str, Any]:
    """Place a graphic behind a matted presenter for one exact time range."""

    record, state, output = _runtime(project_id)
    start = max(0.0, float(start_sec))
    end = float(end_sec)
    if end <= start:
        raise ExportError("end_sec must be after start_sec")
    width, height = _canvas(state)
    props = dict(style_props or {})
    palette = [str(item) for item in props.get("palette", []) if str(item).strip()]
    font = str(props.get("font") or "Inter")
    title = str(props.get("title") or text_or_asset)
    source = Path(text_or_asset).expanduser()

    work = output / "work" / "compositor"
    work.mkdir(parents=True, exist_ok=True)
    if source.is_file():
        graphic_path = source
    else:
        html_path = _cache_path(
            work,
            "depth_graphic",
            title,
            width,
            height,
            palette,
            font,
            end - start,
        )
        html_path = html_path.with_suffix(".html")
        html_path.write_text(
            _graphic_html(
                title=title,
                width=width,
                height=height,
                palette=palette,
                font=font,
                duration=end - start,
            ),
            encoding="utf-8",
        )
        graphic = _render_graphic(
            project_id,
            template_or_code=str(html_path),
            props={**props, "text": title},
            duration=end - start,
            alpha=True,
            width=width,
            height=height,
        )
        graphic_path = Path(str(graphic["output"]))

    trimmed = _trim_clip(project_id, state, start, end)
    matte = _remove_background(project_id, trimmed, is_video=True)
    matted_path = Path(str(matte["output"]))
    created = _append_overlays(
        project_id,
        [
            {
                "path": graphic_path,
                "start_sec": start,
                "end_sec": end,
                "anchor": anchor,
                "width_ratio": width_ratio,
                "z": 10,
            },
            {
                "path": matted_path,
                "start_sec": start,
                "end_sec": end,
                "anchor": "center",
                "width_ratio": 1.0,
                "z": 20,
            },
        ],
        reason="compositor.depth",
    )
    return {
        "ok": True,
        "project_id": project_id,
        "layers": [item.model_dump(mode="json") for item in created],
        "graphic": str(graphic_path),
        "matte": str(matted_path),
        "start_sec": start,
        "end_sec": end,
        "revision": load_project_state(record).revision,
    }


def picture_in_picture(
    project_id: str,
    overlay_asset: str,
    start_sec: float,
    end_sec: float,
    *,
    anchor: str = "bottom_right",
    corner_radius: int = 24,
    width_ratio: float = 0.28,
    margin_x: int = 32,
    margin_y: int = 32,
    z: int = 25,
) -> dict[str, Any]:
    """Add a rounded-window PiP overlay with a cached alpha mask."""

    _record, state, output = _runtime(project_id)
    start = max(0.0, float(start_sec))
    end = float(end_sec)
    if end <= start:
        raise ExportError("end_sec must be after start_sec")
    asset = Path(overlay_asset).expanduser()
    if not asset.is_file():
        raise ExportError(f"PiP asset does not exist: {asset}")
    width, height = _canvas(state)
    ratio = max(0.05, min(0.9, float(width_ratio)))
    pip_width = _even(round(width * ratio))
    source_ratio = _asset_ratio(asset)
    pip_height = _even(max(2, round(pip_width / source_ratio)))
    if pip_height > height:
        pip_height = _even(round(height * 0.9))
        pip_width = _even(round(pip_height * source_ratio))
    radius = max(0, min(pip_width, pip_height, int(corner_radius)))
    mask = ensure_rounded_mask(pip_width, pip_height, radius)
    if mask is None:
        raise ExportError("Pillow is required for rounded PiP masks")
    work = output / "work" / "compositor"
    work.mkdir(parents=True, exist_ok=True)
    target = _cache_path(
        work,
        f"{asset.stem}_pip",
        str(asset.resolve()),
        pip_width,
        pip_height,
        radius,
        asset.stat().st_mtime_ns,
    ).with_suffix(".webm")
    if not target.is_file():
        _rounded_clip(asset, mask, target, pip_width, pip_height, end - start)
    created = _append_overlays(
        project_id,
        [
            {
                "path": target,
                "start_sec": start,
                "end_sec": end,
                "anchor": anchor,
                "margin_x": margin_x,
                "margin_y": margin_y,
                "width_ratio": ratio,
                "z": z,
            }
        ],
        reason="compositor.pip",
    )
    overlay = created[0]
    return {
        "ok": True,
        "project_id": project_id,
        "overlay": overlay.model_dump(mode="json"),
        "asset": str(target),
        "mask": str(mask),
        "width": pip_width,
        "height": pip_height,
    }


def _asset_ratio(path: Path) -> float:
    binary = find_binary("ffprobe")
    if binary is not None:
        completed = subprocess.run(
            [
                binary,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "default=noprint_wrappers=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        values: dict[str, int] = {}
        for line in completed.stdout.splitlines():
            key, _, raw = line.partition("=")
            if key in {"width", "height"}:
                try:
                    values[key] = int(raw)
                except ValueError:
                    continue
        width = values.get("width", 0)
        height = values.get("height", 0)
        if width > 0 and height > 0:
            return width / height
    return 16 / 9


def _rounded_clip(
    asset: Path,
    mask: Path,
    target: Path,
    width: int,
    height: int,
    duration: float,
) -> None:
    image = asset.suffix.casefold() in IMAGE_SUFFIXES
    inputs = (
        ["-loop", "1", "-t", f"{duration:.4f}", "-i", str(asset)]
        if image
        else ["-i", str(asset)]
    )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *inputs,
            "-loop",
            "1",
            "-i",
            str(mask),
            "-filter_complex",
            (
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1[fg];"
                f"[1:v]scale={width}:{height},format=gray[m];"
                "[fg][m]alphamerge[out]"
            ),
            "-map",
            "[out]",
            "-an",
            "-t",
            f"{duration:.4f}",
            "-c:v",
            "libvpx-vp9",
            "-pix_fmt",
            "yuva420p",
            "-b:v",
            "0",
            "-crf",
            "26",
            str(target),
        ],
        what="rounded PiP",
    )


def parallax(
    project_id: str,
    image_path: str,
    start_sec: float,
    end_sec: float,
    *,
    bg_scale: float = 1.04,
    fg_scale: float = 1.12,
    rotate_y_deg: float = 3.0,
    width_ratio: float = 0.72,
    z: int = 10,
) -> dict[str, Any]:
    """Split a still into background and subject layers and animate 2.5D depth."""

    _record, state, output = _runtime(project_id)
    start = max(0.0, float(start_sec))
    end = float(end_sec)
    if end <= start:
        raise ExportError("end_sec must be after start_sec")
    image = Path(image_path).expanduser()
    if not image.is_file():
        raise ExportError(f"Parallax image does not exist: {image}")
    if image.suffix.casefold() not in IMAGE_SUFFIXES:
        raise ExportError("Parallax requires a still image")
    width, height = _canvas(state)
    subject = _remove_background(project_id, image, is_video=False)
    subject_path = Path(str(subject["output"]))
    work = output / "work" / "compositor"
    work.mkdir(parents=True, exist_ok=True)
    html_path = _cache_path(
        work,
        "parallax",
        str(image.resolve()),
        str(subject_path.resolve()),
        width,
        height,
        round(bg_scale, 3),
        round(fg_scale, 3),
        round(rotate_y_deg, 3),
        round(end - start, 3),
    ).with_suffix(".html")
    html_path.write_text(
        _parallax_html(
            image_path=image,
            subject_path=subject_path,
            width=width,
            height=height,
            duration=end - start,
            bg_scale=max(1.0, min(1.2, float(bg_scale))),
            fg_scale=max(1.0, min(1.3, float(fg_scale))),
            rotate_y=max(-12.0, min(12.0, float(rotate_y_deg))),
        ),
        encoding="utf-8",
    )
    graphic = _render_graphic(
        project_id,
        template_or_code=str(html_path),
        props={"bg_scale": bg_scale, "fg_scale": fg_scale, "rotate_y_deg": rotate_y_deg},
        duration=end - start,
        alpha=False,
        width=width,
        height=height,
    )
    created = _append_overlays(
        project_id,
        [
            {
                "path": Path(str(graphic["output"])),
                "start_sec": start,
                "end_sec": end,
                "anchor": "center",
                "width_ratio": width_ratio,
                "z": z,
            }
        ],
        reason="compositor.parallax",
    )
    overlay = created[0]
    return {
        "ok": True,
        "project_id": project_id,
        "overlay": overlay.model_dump(mode="json"),
        "graphic": graphic["output"],
        "subject": str(subject_path),
        "layers": 2,
    }


def _style_frame(
    state: ProjectState,
    work: Path,
    width: int,
    height: int,
) -> Path | None:
    """Extract one graded-looking source frame for the style card (advisory)."""

    media = state.media_info
    if media is None or not media.source_path:
        return None
    source = Path(media.source_path).expanduser()
    if not source.is_file():
        return None
    start = 0.0
    if state.video_segments:
        first = min(state.video_segments, key=lambda item: item.timeline_in_frame)
        start = first.source_in_frame * media.fps_den / max(1, media.fps_num)
    target = _cache_path(
        work,
        "style_frame",
        str(source.resolve()),
        source.stat().st_mtime_ns,
        round(start, 3),
        width,
        height,
    ).with_suffix(".png")
    if target.is_file():
        return target
    binary = find_binary("ffmpeg")
    if binary is None:
        return None
    completed = subprocess.run(
        [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},eq=saturation=1.08:contrast=1.03"
            ),
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not target.is_file():
        return None
    return target


def style_preview(
    project_id: str,
    style_id: str,
    *,
    duration_sec: float = 5.0,
) -> dict[str, Any]:
    """Render a short style card with the style palette, font, and caption."""

    from videoflow.application.style_catalog import StyleCatalog
    from videoflow.domain.errors import StyleNotFoundError

    _record, state, output = _runtime(project_id)
    try:
        style = StyleCatalog().get(style_id)
    except StyleNotFoundError as exc:
        raise ExportError(str(exc)) from exc
    duration = max(1.0, min(30.0, float(duration_sec)))
    width, height, ratio = _preview_canvas(state, style.aspect_ratio)
    palette = [str(item) for item in style.palette if str(item).strip()]
    font = style.fonts[0] if style.fonts else "Inter"
    caption = style.hook_strategy or style.name
    work = output / "work" / "compositor"
    work.mkdir(parents=True, exist_ok=True)
    frame = _style_frame(state, work, width, height)
    html_path = _cache_path(
        work,
        f"style_{style.style_id}",
        style.style_id,
        style.name,
        style.caption_preset,
        style.layout_mode,
        palette,
        font,
        width,
        height,
        round(duration, 3),
        str(frame) if frame else "",
    ).with_suffix(".html")
    html_path.write_text(
        _style_html(
            style_name=style.name,
            style_id=style.style_id,
            layout=style.layout_mode,
            caption=caption,
            width=width,
            height=height,
            palette=palette,
            font=font,
            duration=duration,
            background_image=frame,
        ),
        encoding="utf-8",
    )
    graphic = _render_graphic(
        project_id,
        template_or_code=str(html_path),
        props={"style_id": style.style_id, "palette": palette, "font": font},
        duration=duration,
        alpha=False,
        width=width,
        height=height,
        draft=True,
    )
    return {
        "ok": True,
        "project_id": project_id,
        "style_id": style.style_id,
        "path": graphic["output"],
        "duration_sec": duration,
        "width": width // 2,
        "height": height // 2,
        "aspect_ratio": ratio,
        "palette": palette,
        "font": font,
        "draft": True,
        "source_frame": str(frame) if frame else "",
    }


def _preview_canvas(state: ProjectState, aspect_ratio: str) -> tuple[int, int, str]:
    ratio = str(aspect_ratio or "").strip()
    presets = {
        "9:16": (1080, 1920),
        "4:5": (1080, 1350),
        "3:4": (1080, 1440),
        "2:3": (1080, 1620),
        "1:1": (1080, 1080),
        "16:9": (1920, 1080),
    }
    if ratio in presets:
        width, height = presets[ratio]
        return width, height, ratio
    width, height = _canvas(state)
    return width, height, ratio or ("9:16" if height > width else "16:9")


__all__ = [
    "depth_composite",
    "parallax",
    "picture_in_picture",
    "style_preview",
]
