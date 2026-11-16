"""Deterministic HTML-to-video rendering through a local Chromium.

The renderer seeks each frame through the page fragment (``#t=<seconds>``), so
HTML/GSAP/Three.js scenes can implement a deterministic timeline without a
Node server. Remotion/Hyperframes projects keep using their own CLI command.
"""

from __future__ import annotations

import hashlib
import json
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


def _scene_cache_key(
    root: Path,
    page: Path,
    *,
    duration_sec: float,
    fps: int,
    width: int,
    height: int,
    alpha: bool,
    draft_scale: float,
    browser: str,
) -> str:
    hasher = hashlib.sha256()
    files = [page] if page.is_file() else []
    if root.is_dir():
        files.extend(path for path in sorted(root.rglob("*")) if path.is_file() and path != page)
    for path in files:
        hasher.update(str(path.relative_to(root)).encode("utf-8"))
        hasher.update(path.read_bytes())
    browser_stat = Path(browser).stat() if Path(browser).is_file() else None
    hasher.update(
        json.dumps(
            {
                "duration": round(duration_sec, 4),
                "fps": fps,
                "width": width,
                "height": height,
                "alpha": alpha,
                "draft_scale": round(draft_scale, 4),
                "browser": browser,
                "browser_mtime": browser_stat.st_mtime_ns if browser_stat else 0,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return hasher.hexdigest()


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
    timeout: float = 900.0,
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
    cache_key = _scene_cache_key(
        root,
        page,
        duration_sec=duration_sec,
        fps=fps,
        width=width,
        height=height,
        alpha=alpha,
        draft_scale=draft_scale,
        browser=browser,
    )
    cache_path = target.with_suffix(target.suffix + ".cache.json")
    if target.is_file() and target.stat().st_size > 0 and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = {}
        if isinstance(cached, dict) and cached.get("key") == cache_key:
            return target
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
    cache_path.write_text(
        json.dumps({"key": cache_key, "target": str(target)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


__all__ = ["browser_binary", "render_html_scene"]
