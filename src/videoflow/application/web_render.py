"""Deterministic HTML-to-video rendering through a local Chromium.

The renderer seeks each frame through the page fragment (``#t=<seconds>``), so
HTML/GSAP/Three.js scenes can implement a deterministic timeline without a
Node server. Remotion/Hyperframes projects keep using their own CLI command.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from videoflow.application.render_gate import render_gate
from videoflow.runtime import find_binary


def browser_binary() -> str | None:
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = find_binary(name)
        if found:
            return found
    return None


def _screenshot(
    browser: str,
    url: str,
    target: Path,
    width: int,
    height: int,
    *,
    alpha: bool,
) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        "--virtual-time-budget=1000",
        f"--screenshot={target}",
    ]
    if alpha:
        command.insert(-1, "--default-background-color=00000000")
    command.append(url)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return completed.returncode == 0 and target.is_file()


def render_html_scene(  # pragma: no cover - external Chromium runtime
    project: Path,
    entry: str,
    output: Path,
    *,
    duration_sec: float,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    alpha: bool = False,
    draft_scale: float = 1.0,
) -> Path:
    browser = browser_binary()
    if browser is None:
        raise RuntimeError("No Chrome/Chromium binary was found.")
    root = Path(project).expanduser()
    page = (root / entry) if root.is_dir() else root
    if not page.is_file():
        raise FileNotFoundError(f"HTML scene entry not found: {page}")
    frame_width = max(16, int(width * draft_scale))
    frame_height = max(16, int(height * draft_scale))
    target = Path(output).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    frames = target.parent / f".{target.stem}-frames"
    if frames.exists():
        for item in frames.iterdir():
            item.unlink()
    frames.mkdir(parents=True, exist_ok=True)
    total = max(1, int(round(duration_sec * fps)))
    with render_gate.hold("web_render", target.name):
        for index in range(total):
            time_sec = index / max(1, fps)
            url = f"{page.resolve().as_uri()}#t={time_sec:.3f}"
            frame = frames / f"frame-{index:05d}.png"
            if not _screenshot(browser, url, frame, frame_width, frame_height, alpha=alpha):
                raise RuntimeError(f"Chrome did not render frame {index} for {page.name}")
        ffmpeg = find_binary("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("FFmpeg is required to encode the web scene.")
        suffix = ".mov" if alpha else ".mp4"
        if target.suffix.lower() != suffix:
            target = target.with_suffix(suffix)
        temporary = target.with_name(f".{target.stem}.part{target.suffix}")
        codec = (
            ["-c:v", "qtrle", "-pix_fmt", "argb"]
            if alpha
            else [
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                "18",
                "-preset",
                "veryfast",
            ]
        )
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(frames / "frame-%05d.png"),
                *codec,
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Web scene encode failed: {completed.stderr.strip()[-800:]}")
        temporary.replace(target)
        for item in frames.iterdir():
            item.unlink()
        frames.rmdir()
    return target


__all__ = ["browser_binary", "render_html_scene"]
