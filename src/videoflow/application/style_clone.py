"""Channel style cloning and rule learning used by ``vf_project``."""

# The two helpers below run the same steps used by the recipe engine so the
# MCP surface and the pipeline never diverge.

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from videoflow.application.preset_rules import load_rulebook, save_rulebook
from videoflow.core.context import PipelineContext
from videoflow.runtime import find_binary
from videoflow.steps.base import StepIO
from videoflow.steps.preset_compile import CompileRuleParams, CompileRuleStep
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


def clone_style(
    channel_id: str,
    output: Path,
    *,
    reference_url: str = "",
    reference_dir: str = "",
    images: list[str] | None = None,
    name: str = "",
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
    book = load_rulebook(channel_id)
    book.channel_id = channel_id
    palette = [str(item) for item in preset.get("palette") or []]
    if palette:
        book.channel_kit.palette = palette
    typography = preset.get("typography") or {}
    family = str(typography.get("family") or "").strip()
    if family:
        book.channel_kit.fonts = [family]
    book.channel_kit.defaults.setdefault("style", {})
    book.channel_kit.defaults["style"] = {
        "preset": preset,
        "safe_zones": preset.get("safe_zones") or {},
    }
    path = save_rulebook(book)
    return {
        "ok": True,
        "channel_id": channel_id,
        "preset": preset,
        "rulebook": str(path),
        "resource": f"vf://presets/{channel_id}/kit",
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
) -> dict[str, Any]:
    """Compile human review notes into the channel rulebook."""

    context = _context(Path(output))
    CompileRuleStep().run(
        context,
        CompileRuleParams(
            channel_id=channel_id,
            review_notes=list(notes or []),
            mode=mode,  # type: ignore[arg-type]
            max_rules=max(1, min(15, int(max_rules))),
        ),
        StepIO(stage="preset.compile_rule"),
    )
    book = context.metadata.get("preset_rulebook") or {}
    return {
        "ok": True,
        "channel_id": channel_id,
        "rulebook": context.artifacts.get("preset_rulebook", ""),
        "resource": f"vf://presets/{channel_id}/rulebook",
        "rules": book.get("learned_rules", []),
        "count": len(book.get("learned_rules", [])),
        "warnings": list(context.warnings),
    }


__all__ = ["clone_style", "learn_rule"]
