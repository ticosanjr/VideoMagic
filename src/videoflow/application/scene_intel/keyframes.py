"""One on-demand JPEG keyframe per scene."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.scene_intel.detect import SceneSpan
from videoflow.application.scene_intel.proxy import KEYFRAME_QUALITY, KEYFRAME_SIZE


def scene_keyframe_path(keyframes_dir: Path, scene_id: str) -> Path:
    return Path(keyframes_dir) / f"{scene_id}.jpg"


def keyframe_timestamp(span: SceneSpan) -> float:
    return round(span.start_sec + span.duration / 2.0, 6)


def _batch_keyframes(
    source: Path,
    spans: list[SceneSpan],
    directory: Path,
    *,
    scene_ids: list[str],
    fps: float,
    size: int,
    quality: int,
) -> tuple[list[str], list[str]] | None:
    """Extract all scene midpoints in one decode pass."""

    frames = sorted({max(0, round((span.start_sec + span.duration / 2.0) * fps)) for span in spans})
    if len(frames) != len(spans):
        return None
    expression = "+".join(f"eq(n\\,{frame})" for frame in frames)
    limit = max(64, int(size))
    scale = (
        f"scale='if(gt(iw,ih),{limit},-2)':"
        f"'if(gt(iw,ih),-2,{limit})':flags=lanczos"
    )
    qscale = max(2, min(31, round(31 - (max(1, min(100, quality)) * 0.29))))
    with tempfile.TemporaryDirectory(prefix="vf-keyframes-") as temporary:
        temp_dir = Path(temporary)
        pattern = temp_dir / "SC_%04d.jpg"
        graph = f"select='{expression}',{scale}"
        argv = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
        ]
        script_path: Path | None = None
        if len(graph) > 3000:
            script_path = temp_dir / "keyframes.filter"
            script_path.write_text(graph, encoding="utf-8")
            argv.extend(["-filter_script:v", str(script_path)])
        else:
            argv.extend(["-vf", graph])
        argv.extend(
            [
                "-vsync",
                "0",
                "-frames:v",
                str(len(spans)),
                "-q:v",
                str(qscale),
                str(pattern),
            ]
        )
        completed = subprocess.run(
            argv, capture_output=True, text=True, check=False, timeout=600
        )
        if completed.returncode != 0:
            return None
        produced = sorted(temp_dir.glob("SC_*.jpg"))
        if len(produced) != len(spans):
            return None
        paths: list[str] = []
        for scene_id, produced_path in zip(scene_ids, produced, strict=False):
            target = scene_keyframe_path(directory, scene_id)
            shutil.move(str(produced_path), str(target))
            paths.append(str(target))
        return paths, []


def extract_scene_keyframes(
    source: Path,
    spans: list[SceneSpan],
    keyframes_dir: Path,
    *,
    scene_ids: list[str] | None = None,
    size: int = KEYFRAME_SIZE,
    quality: int = KEYFRAME_QUALITY,
    fps: float = 30.0,
    force: bool = False,
) -> tuple[list[str], list[str]]:
    """Write one small JPEG per scene and return paths plus warnings."""

    adapter = FFmpegAdapter()
    directory = Path(keyframes_dir)
    directory.mkdir(parents=True, exist_ok=True)
    ids = scene_ids or [f"SC_{index + 1:04d}" for index in range(len(spans))]
    paths = [str(scene_keyframe_path(directory, scene_id)) for scene_id in ids]
    warnings: list[str] = []
    if not spans:
        return [], []
    if all(Path(path).is_file() for path in paths) and not force:
        return paths, []
    if len(spans) >= 4:
        batched = _batch_keyframes(
            source,
            spans,
            directory,
            scene_ids=ids,
            fps=fps,
            size=size,
            quality=quality,
        )
        if batched is not None:
            return batched

    def one(index: int) -> tuple[str, str]:
        scene_id = scene_ids[index] if scene_ids else f"SC_{index + 1:04d}"
        target = scene_keyframe_path(directory, scene_id)
        if target.is_file() and target.stat().st_size > 0 and not force:
            return str(target), ""
        try:
            adapter.extract_keyframe(
                source,
                target,
                time_sec=keyframe_timestamp(spans[index]),
                max_size=size,
                quality=quality,
            )
        except Exception as exc:  # noqa: BLE001 - a missing frame must not abort analysis
            if target.exists():
                target.unlink(missing_ok=True)
            return "", f"Keyframe {scene_id} failed: {exc}"
        return str(target), ""

    workers = min(8, max(1, os.cpu_count() or 4), max(1, len(spans)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, range(len(spans))))
    paths = [item[0] for item in results]
    warnings = [item[1] for item in results if item[1]]
    return paths, warnings


__all__ = [
    "extract_scene_keyframes",
    "keyframe_timestamp",
    "scene_keyframe_path",
]
