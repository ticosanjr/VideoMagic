# ruff: noqa: E501
"""HTML/CSS scene rendering with an FFmpeg fallback.

The scene graph stays JSON-only. Each scene also gets a self-contained HTML
document; a headless browser renders it when Playwright and Chromium are
installed, and FFmpeg renders the JSON graph otherwise.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from videoflow.application.motion import render_scene
from videoflow.runtime import find_binary


def _css_color(value: str, fallback: str) -> str:
    text = str(value or "").strip()
    if text.startswith("#") and len(text) in {4, 7}:
        return text
    return fallback


def _asset_uri(path: str) -> str:
    candidate = Path(path).expanduser()
    return candidate.resolve().as_uri() if candidate.is_file() else ""


def scene_html(
    scene: dict[str, Any],
    *,
    title_style: str = "lower_third",
    three_js: bool = False,
) -> str:
    background = _css_color(str(scene.get("background") or ""), "#080B10")
    accent = _css_color(str(scene.get("accent") or ""), "#FF3B30")
    text_color = _css_color(str(scene.get("text_color") or ""), "#F8FAFC")
    duration = max(1.0, float(scene.get("duration_sec") or 5.0))
    width = int(scene.get("width") or 1920)
    layers = [item for item in scene.get("layers") or [] if isinstance(item, dict)]
    asset = next(
        (item for item in layers if item.get("type") in {"image", "video"} and item.get("path")),
        None,
    )
    title = str((asset or {}).get("text") or scene.get("title") or "")
    narration = str(scene.get("narration") or "")
    asset_markup = ""
    if asset is not None:
        uri = _asset_uri(str(asset.get("path") or ""))
        if uri:
            if asset.get("type") == "video":
                asset_markup = (
                    f'<video id="asset" class="asset" src="{uri}" muted playsinline '
                    f'preload="auto"></video>'
                )
            else:
                asset_markup = f'<img id="asset" class="asset" src="{uri}" alt="">'
    panels = "".join(
        f'<div class="panel" style="animation-delay:{float(layer.get("start_sec") or 0.2):.3f}s">'
        f"{str(layer.get('text') or '')}</div>"
        for layer in layers
        if layer.get("type") in {"lower_third", "panel"} and layer.get("text")
    )
    animation = (
        "fadeUp 0.7s cubic-bezier(.2,.8,.2,1) both"
        if title_style == "lower_third"
        else "fadeIn 0.7s ease-out both"
    )
    three_script = (
        """<script type="module">
import * as THREE from './three.module.js';
const canvas = document.getElementById('three-canvas');
const renderer = new THREE.WebGLRenderer({canvas, alpha: true, antialias: true});
const scene3d = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
camera.position.set(0, 0, 6);
const geometry = new THREE.PlaneGeometry(4.6, 2.6, 32, 32);
const material = new THREE.MeshStandardMaterial({color: 0x0f172a, roughness: 0.55, metalness: 0.25, side: THREE.DoubleSide});
const mesh = new THREE.Mesh(geometry, material);
scene3d.add(mesh);
const light = new THREE.DirectionalLight(0xffffff, 2.4);
light.position.set(3, 4, 5);
scene3d.add(light);
scene3d.add(new THREE.AmbientLight(0xffffff, 0.7));
function resize3d() {
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  camera.aspect = window.innerWidth / Math.max(1, window.innerHeight);
  camera.updateProjectionMatrix();
}
window.threeSetTime = (t) => {
  mesh.rotation.y = Math.sin(t * 0.6) * 0.12;
  mesh.rotation.x = Math.sin(t * 0.35) * 0.04;
  camera.position.x = Math.sin(t * 0.35) * 0.25;
  camera.lookAt(0, 0, 0);
  renderer.render(scene3d, camera);
};
window.addEventListener('resize', resize3d);
resize3d();
window.threeSetTime(0);
</script>"""
        if three_js
        else ""
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>{title or scene.get("scene_id", "VideoFlow scene")}</title>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; background: {background}; }}
  #stage {{
    position: relative; width: 100%; height: 100%; overflow: hidden;
    font-family: Inter, "DejaVu Sans", Arial, sans-serif; color: {text_color};
    perspective: 1200px; background:
      radial-gradient(circle at 18% 12%, {accent}33, transparent 42%),
      linear-gradient(135deg, {background}, #000000);
  }}
  .asset {{
    position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;
    opacity: .72; filter: saturate(1.05) contrast(1.05);
  }}
  #three-canvas {{
    position: absolute; inset: 0; width: 100%; height: 100%; z-index: 0;
  }}
  .vignette {{
    position: absolute; inset: 0;
    background: linear-gradient(180deg, transparent 40%, #000000cc 100%);
  }}
  .plane {{
    position: absolute; left: 8%; top: 18%; width: 54%; padding: 28px 34px;
    border: 2px solid {accent}aa; border-radius: 22px;
    background: linear-gradient(135deg, #0f172acc, #020617dd);
    box-shadow: 0 30px 90px #00000088;
    transform: rotateY(8deg) rotateX(3deg) translateZ(40px);
    animation: {animation};
  }}
  .kicker {{ font-size: {max(14, width // 80)}px; letter-spacing: .18em; text-transform: uppercase; color: {accent}; }}
  h1 {{ margin: 12px 0 0; font-size: {max(34, width // 28)}px; line-height: 1.06; }}
  .narration {{ margin-top: 14px; font-size: {max(16, width // 72)}px; line-height: 1.45; opacity: .82; }}
  .panel {{
    position: absolute; left: 8%; bottom: 8%; max-width: 62%;
    padding: 16px 22px; border-left: 6px solid {accent};
    border-radius: 12px; background: #020617dd; font-size: {max(16, width // 80)}px;
    animation: fadeUp .6s cubic-bezier(.2,.8,.2,1) both;
  }}
  .meter {{ position: absolute; right: 7%; bottom: 9%; width: 150px; height: 6px; background: #ffffff22; border-radius: 99px; overflow: hidden; }}
  .meter::after {{ content: ""; display: block; height: 100%; width: 38%; background: {accent}; animation: grow {duration:.3f}s ease-out both; }}
  @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(28px) rotateY(8deg) rotateX(3deg) translateZ(40px); }} to {{ opacity: 1; transform: translateY(0) rotateY(8deg) rotateX(3deg) translateZ(40px); }} }}
  @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
  @keyframes grow {{ from {{ width: 0; }} to {{ width: 38%; }} }}
</style>
</head>
<body>
<div id="stage">
  {('<canvas id="three-canvas"></canvas>' if three_js else "")}
  {asset_markup}
  <div class="vignette"></div>
  <div class="plane">
    <div class="kicker">{scene.get("scene_id", "")}</div>
    <h1>{title}</h1>
    <div class="narration">{narration[:220]}</div>
  </div>
  {panels}
  <div class="meter"></div>
</div>
<script>
  window.setTime = (seconds) => {{
    if (window.threeSetTime) {{
      try {{ window.threeSetTime(seconds); }} catch (error) {{}}
    }}
    const video = document.getElementById('asset');
    if (video && video.tagName === 'VIDEO') {{
      try {{ video.currentTime = seconds; }} catch (error) {{}}
    }}
    for (const animation of document.getAnimations()) {{
      animation.pause();
      try {{ animation.currentTime = seconds * 1000; }} catch (error) {{}}
    }}
  }};
</script>
{three_script}
</body>
</html>
"""


def write_scene_html(
    scene: dict[str, Any],
    directory: Path,
    *,
    title_style: str,
    three_js: bool = False,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    scene_id = str(scene.get("scene_id") or "SCENE")
    target = directory / f"{scene_id}.html"
    target.write_text(
        scene_html(scene, title_style=title_style, three_js=three_js),
        encoding="utf-8",
    )
    return target


def render_html_scene(
    html_path: Path,
    target: Path,
    *,
    duration_sec: float,
    fps: int,
    width: int,
    height: int,
    draft_scale: float = 1.0,
    timeout: float = 600.0,
) -> Path:
    """Render one HTML scene to MP4 with Playwright; raises when unavailable."""

    from playwright.sync_api import sync_playwright

    binary = find_binary("ffmpeg")
    if binary is None:
        raise RuntimeError("FFmpeg is not available.")
    try:
        from importlib.metadata import version as package_version

        playwright_version = package_version("playwright")
    except Exception:  # noqa: BLE001 - optional metadata
        playwright_version = ""
    cache_key = hashlib.sha256(
        html_path.read_bytes()
        + json.dumps(
            {
                "duration": round(duration_sec, 4),
                "fps": fps,
                "width": width,
                "height": height,
                "draft_scale": round(draft_scale, 4),
                "playwright": playwright_version,
                "ffmpeg": binary,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    cache_path = target.with_suffix(target.suffix + ".cache.json")
    if target.is_file() and target.stat().st_size > 0 and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = {}
        if isinstance(cached, dict) and cached.get("key") == cache_key:
            return target
    frames_dir = target.with_name(f".{target.stem}-frames")
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    scale = max(0.1, min(1.0, draft_scale))
    viewport = {
        "width": max(2, int(width * scale)),
        "height": max(2, int(height * scale)),
    }
    frame_count = max(1, round(max(0.5, duration_sec) * fps))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--allow-file-access-from-files",
                    "--disable-web-security",
                ],
            )
            page = browser.new_page(viewport=viewport)
            page.goto(html_path.resolve().as_uri())
            page.wait_for_timeout(120)
            for index in range(frame_count):
                page.evaluate("seconds => window.setTime(seconds)", index / fps)
                page.screenshot(path=str(frames_dir / f"frame-{index:05d}.png"))
            browser.close()
    except Exception:
        shutil.rmtree(frames_dir, ignore_errors=True)
        raise
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame-%05d.png"),
        "-vf",
        f"scale={width}:{height}:flags=lanczos",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=max(30.0, timeout))
    shutil.rmtree(frames_dir, ignore_errors=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Could not encode the HTML scene: "
            + (completed.stderr.strip() or f"exit {completed.returncode}")
        )
    cache_path.write_text(
        json.dumps({"key": cache_key, "target": str(target)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def render_scene_ffmpeg(
    scene: dict[str, Any], output_dir: Path, *, draft_scale: float = 1.0
) -> Path:
    return render_scene(scene, output_dir, draft_scale=draft_scale)


def _concat_line(path: Path) -> str:
    escaped = str(path).replace("'", "'\\''")
    return f"file '{escaped}'"


def concatenate(paths: list[Path], target: Path) -> Path:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise RuntimeError("FFmpeg is not available.")
    if not paths:
        raise RuntimeError("No rendered scenes to assemble.")
    target.parent.mkdir(parents=True, exist_ok=True)
    list_path = target.with_suffix(".concat.txt")
    list_path.write_text(
        "\n".join(_concat_line(path) for path in paths) + "\n",
        encoding="utf-8",
    )
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    with contextlib.suppress(OSError):
        list_path.unlink()
    if completed.returncode != 0:
        raise RuntimeError(
            "Could not assemble the scenes: "
            + (completed.stderr.strip() or f"exit {completed.returncode}")
        )
    return target


def mux_master(
    video: Path,
    audio: Path,
    target: Path,
    *,
    subtitles: Path | None = None,
) -> Path:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise RuntimeError("FFmpeg is not available.")
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [binary, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    if audio.is_file():
        command.extend(["-i", str(audio)])
    filters: list[str] = []
    if subtitles is not None and subtitles.is_file():
        escaped = str(subtitles).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        filters.append(f"ass='{escaped}'")
    if filters:
        command.extend(["-vf", ",".join(filters)])
    command.extend(["-map", "0:v:0"])
    if audio.is_file():
        command.extend(["-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-shortest"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(target),
        ]
    )
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Could not assemble the master: "
            + (completed.stderr.strip() or f"exit {completed.returncode}")
        )
    return target


def write_manifest(directory: Path, scenes: list[dict[str, Any]]) -> Path:
    target = Path(directory) / "render-manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"scenes": scenes, "count": len(scenes)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return target
