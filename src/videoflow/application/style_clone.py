"""Channel style cloning and rule learning used by ``vf_project``."""

# The two helpers below run the same steps used by the recipe engine so the
# MCP surface and the pipeline never diverge.

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from videoflow.application.style_catalog import (
    catalog as style_catalog,
)
from videoflow.application.style_catalog import style_slug
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import StyleNotFoundError
from videoflow.domain.styles import StyleDefinition
from videoflow.runtime import find_binary
from videoflow.steps.base import StepIO
from videoflow.steps.style_reverse import StyleReverseParams, StyleReverseStep

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def _capture_reference(url: str, target: Path) -> str:
    browser = find_binary("google-chrome", "chromium", "chromium-browser", "chrome")
    if browser is None:
        return "chromium_not_found"
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--window-size=1440,900",
            "--virtual-time-budget=2500",
            f"--screenshot={target}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0 or not target.is_file():
        return (completed.stderr.strip() or "capture_failed")[-300:]
    return ""


def _download_reference_video(url: str, output: Path) -> Path | None:
    """Download a short, low-risk reference segment with yt-dlp when available."""

    binary = find_binary("yt-dlp")
    if binary is None:
        return None
    target = output / "style" / "reference.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            binary,
            "--no-playlist",
            "--max-filesize",
            "200M",
            "--download-sections",
            "*0-45",
            "--force-keyframes-at-cuts",
            "-f",
            "mp4/best",
            "-o",
            str(target),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0 or not target.is_file():
        return None
    return target


def _sample_video_frames(video: Path, output: Path, *, limit: int = 8) -> list[str]:
    ffmpeg = find_binary("ffmpeg")
    if ffmpeg is None:
        return []
    directory = output / "style" / "frames"
    directory.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            "fps=1/4,scale=640:-2",
            "-frames:v",
            str(limit),
            str(directory / "frame-%03d.png"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0:
        return []
    return [str(path) for path in sorted(directory.glob("frame-*.png"))]


def _cut_rhythm(video: Path) -> dict[str, Any] | None:
    """Estimate the cut rhythm from FFmpeg scene-change timestamps."""

    ffmpeg = find_binary("ffmpeg")
    if ffmpeg is None:
        return None
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(video),
            "-vf",
            "select='gt(scene,0.35)',showinfo",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    times = sorted(
        float(value) for value in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", completed.stderr)
    )
    deltas = [round(b - a, 3) for a, b in zip(times, times[1:], strict=False) if b > a]
    if not deltas:
        return None
    deltas.sort()
    middle = deltas[len(deltas) // 2]
    return {
        "mode": "measured",
        "min_cut_sec": deltas[0],
        "max_cut_sec": deltas[-1],
        "median_cut_sec": middle,
    }


def _context(output: Path) -> PipelineContext:
    return PipelineContext(
        source=Path(output),
        output=Path(output),
        work=Path(output) / "style" / "work",
        exports=Path(output) / "exports",
    )


def _style_body(preset: dict[str, Any], reference_url: str) -> str:
    palette = ", ".join(str(item) for item in preset.get("palette") or []) or "auto"
    typography = preset.get("typography") or {}
    rhythm = preset.get("cut_rhythm") or {}
    lines = [
        "# Direção Visual & Editorial",
        "",
        f"- Paleta: {palette}",
        f"- Tipografia: {typography.get('family') or 'sans-serif'} "
        f"({typography.get('weight') or 'bold'}, {typography.get('case') or 'normal'})",
        "- Ritmo de corte: "
        f"{rhythm.get('median_cut_sec') or rhythm.get('max_cut_sec') or 'reference'}s",
        "- Safe zones: reels, tiktok, shorts",
    ]
    if reference_url:
        lines.append(f"- Referência: {reference_url}")
    return "\n".join(lines)


def clone_style(
    channel_id: str,
    output: Path,
    *,
    reference_url: str = "",
    reference_dir: str = "",
    images: list[str] | None = None,
    name: str = "",
    workspace_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Extract palette, typography hints, rhythm, and safe zones into a kit."""

    output = Path(output).expanduser()
    files = [str(Path(item).expanduser()) for item in (images or [])]
    warnings: list[str] = []
    rhythm: dict[str, Any] | None = None
    if reference_dir:
        directory = Path(reference_dir).expanduser()
        if directory.is_dir():
            for path in sorted(directory.iterdir()):
                if not path.is_file():
                    continue
                if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    files.append(str(path))
                elif path.suffix.lower() in VIDEO_SUFFIXES:
                    files.extend(_sample_video_frames(path, output))
                    rhythm = rhythm or _cut_rhythm(path)
    if reference_url:
        video = _download_reference_video(reference_url, output)
        if video is not None:
            files.extend(_sample_video_frames(video, output))
            rhythm = _cut_rhythm(video)
        else:
            target = output / "style" / "reference.png"
            error = _capture_reference(reference_url, target)
            if error:
                warnings.append(f"reference capture failed: {error}")
            else:
                files.append(str(target))
    if not files:
        warnings.append("no reference images or video frames were available")
    context = _context(output)
    StyleReverseStep().run(
        context,
        StyleReverseParams(
            images=files,
            reference_path=reference_url,
            name=name or channel_id or "reference",
        ),
        StepIO(stage="style.reverse_engineer"),
    )
    preset = dict(context.metadata.get("style_preset") or {})
    if rhythm is not None:
        preset["cut_rhythm"] = rhythm
    style_id = style_slug(channel_id or name or "style")
    try:
        style = style_catalog().get(style_id)
    except StyleNotFoundError:
        style = StyleDefinition(style_id=style_id, name=name or channel_id or style_id)
    typography = preset.get("typography") or {}
    fonts = list(style.fonts)
    family = str(typography.get("family") or "").strip()
    if family and family not in fonts:
        fonts = [family, *fonts]
    style = style.model_copy(
        update={
            "name": name or style.name or style_id,
            "palette": [str(item) for item in preset.get("palette") or []] or style.palette,
            "fonts": fonts,
            "cut_rhythm": dict(preset.get("cut_rhythm") or style.cut_rhythm),
            "safe_zones": dict(preset.get("safe_zones") or style.safe_zones),
            "body": _style_body(preset, reference_url),
        }
    )
    path = style_catalog().save(style)
    sync = style_catalog().sync(workspace_dir) if workspace_dir is not None else {}
    return {
        "ok": True,
        "channel_id": style_id,
        "style_id": style_id,
        "preset": preset,
        "style": style.model_dump(mode="json"),
        "rulebook": str(path),
        "file": str(path),
        "resource": f"vf://styles/{style_id}",
        "legacy_resource": f"vf://presets/{style_id}/kit",
        "sync": sync,
        "warnings": warnings,
        "images": files,
    }


def learn_rule(
    channel_id: str,
    output: Path,
    *,
    notes: list[str] | None = None,
    mode: str = "merge",
    max_rules: int = 15,
    workspace_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compile human review notes into the channel rulebook."""

    style_id = style_slug(channel_id or "style")
    try:
        style_catalog().get(style_id)
    except StyleNotFoundError:
        style_catalog().save(StyleDefinition(style_id=style_id, name=channel_id or style_id))
    style = style_catalog().learn_rule(
        style_id,
        list(notes or []),
        mode=mode,
        max_rules=max(1, min(15, int(max_rules))),
    )
    sync = style_catalog().sync(workspace_dir) if workspace_dir is not None else {}
    return {
        "ok": True,
        "channel_id": style_id,
        "style_id": style_id,
        "rulebook": str(style_catalog().root / f"{style_id}.md"),
        "resource": f"vf://styles/{style_id}",
        "legacy_resource": f"vf://presets/{style_id}/rulebook",
        "rules": [rule.model_dump(mode="json") for rule in style.learned_rules],
        "count": len(style.learned_rules),
        "sync": sync,
        "warnings": [],
    }


__all__ = ["clone_style", "learn_rule"]
