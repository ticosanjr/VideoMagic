"""Scene detection, layout classification, and keyframe extraction."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vf_shared.scene_rules import classify_layout as _classify_layout
from vf_shared.scene_rules import editing_hints as _editing_hints

from gpu_worker.gpu_handlers.common import _available, _ffmpeg, _run
from gpu_worker.handlers import Handler, HandlerError
from gpu_worker.progress import report

if TYPE_CHECKING:
    from gpu_worker.settings import Settings

from gpu_worker.gpu_handlers.scene_visual import (
    _scene_visuals,
)


def _scene_ffmpeg_times(
    source: Path,
    *,
    ffmpeg: str,
    threshold: float,
) -> list[float]:
    import re

    mapped = max(0.05, min(0.95, float(threshold) / 8.0))
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(source),
            "-vf",
            f"select='gt(scene,{mapped})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or "").strip().splitlines()
        raise HandlerError(
            f"ffmpeg scene detection failed: {tail[-1][:300] if tail else 'no stderr'}"
        )
    pattern = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")
    return sorted({float(match.group(1)) for match in pattern.finditer(completed.stderr)})


def _scene_detect_times(
    proxy: Path,
    *,
    ffmpeg: str,
    fps: float,
    threshold: float,
    min_scene_len_sec: float,
    analyze_fps: float = 10.0,
) -> list[float]:
    try:
        from scenedetect import SceneManager, open_video
        from scenedetect.detectors import AdaptiveDetector

        video = open_video(str(proxy))
        manager = SceneManager()
        manager.add_detector(
            AdaptiveDetector(
                adaptive_threshold=max(0.1, float(threshold)),
                min_scene_len=max(1, round(fps * max(0.1, min_scene_len_sec))),
                window_width=2,
            )
        )
        manager.detect_scenes(
            video,
            show_progress=False,
            frame_skip=max(0, round(analyze_fps / 10) - 1),
        )
        return [
            float(getattr(scene[0], "seconds", 0.0))
            if hasattr(scene[0], "seconds")
            else scene[0].get_seconds()
            for scene in manager.get_scene_list()
        ]
    except Exception:  # noqa: BLE001 - optional dependency
        return _scene_ffmpeg_times(proxy, ffmpeg=ffmpeg, threshold=threshold)






def _scene_layout(visual: dict[str, Any], width: int, height: int, topology: str) -> str:
    return _classify_layout(
        face_count=int(visual["face_count"]),
        face_area_ratio=float(visual["face_area_ratio"]),
        edge_density=float(visual["edge_density"]),
        width=width,
        height=height,
        topology=topology,
    )


def _scene_hints(
    layout: str,
    duration: float,
    visual: dict[str, Any],
    previous: str | None,
) -> list[str]:
    return _editing_hints(
        layout=layout,
        duration_sec=duration,
        edge_density=float(visual["edge_density"]),
        sharpness_laplacian=float(visual["sharpness_laplacian"]),
        previous_layout=previous,
    )


def _scene_keyframes(
    source: Path,
    spans: list[tuple[float, float]],
    directory: Path,
    *,
    size: int,
) -> list[str]:
    from concurrent.futures import ThreadPoolExecutor

    import cv2

    directory.mkdir(parents=True, exist_ok=True)

    def one(index: int, start: float, end: float) -> str:
        scene_id = f"SC_{index + 1:04d}"
        target = directory / f"{scene_id}.jpg"
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            capture.release()
            return ""
        try:
            capture.set(
                cv2.CAP_PROP_POS_MSEC,
                (start + max(0.0, end - start) / 2.0) * 1000.0,
            )
            ok, frame = capture.read()
        finally:
            capture.release()
        if not ok:
            return ""
        height, width = frame.shape[:2]
        scale = min(1.0, float(size) / max(1, max(width, height)))
        if scale < 1.0:
            frame = cv2.resize(
                frame,
                (max(1, round(width * scale)), max(1, round(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        cv2.imwrite(str(target), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
        return f"keyframes/{scene_id}.jpg"

    workers = min(8, max(1, len(spans)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(
            pool.map(
                lambda item: one(item[0], item[1][0], item[1][1]),
                enumerate(spans),
            )
        )


def make_scene_analyze_handler(settings: Settings) -> Handler:
    """Detect scenes, classify layouts, and return keyframes as a zip."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:

        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("scene_analyze requires a video artifact")
        if not _available("cv2"):
            raise HandlerError("OpenCV is not installed on the worker")
        source = input_paths[0]
        width = max(1, int(params.get("width") or 1920))
        height = max(1, int(params.get("height") or 1080))
        fps = max(1.0, float(params.get("fps") or 30.0))
        sample_rate = max(1, int(params.get("sample_rate") or 48_000))
        duration = max(0.001, float(params.get("duration_sec") or 0.0))
        threshold = float(params.get("threshold") or 3.0)
        min_scene_len_sec = float(params.get("min_scene_len_sec") or 1.5)
        topology = str(params.get("source_topology") or "single_16x9")
        keyframe_size = max(128, min(1080, int(params.get("keyframe_size") or 544)))
        visual_max_frames = max(3, min(5, int(params.get("visual_max_frames") or 3)))
        if topology == "auto":
            ratio = width / max(1, height)
            topology = "dual_canvas" if abs(ratio - 3.55) < 0.15 else "single_16x9"
        ffmpeg = _ffmpeg(settings)
        proxy = work_dir / "proxy_360.mp4"
        analyze_fps = 3.0
        report("building scene proxy", 8)
        _run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-vf",
                "scale=-2:360",
                "-r",
                str(int(analyze_fps)),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                str(proxy),
            ]
        )
        report("detecting cuts", 30)
        times = _scene_detect_times(
            proxy,
            ffmpeg=ffmpeg,
            fps=analyze_fps,
            threshold=threshold,
            min_scene_len_sec=min_scene_len_sec,
            analyze_fps=analyze_fps,
        )
        boundaries = sorted(
            {
                0.0,
                *[t for t in times if 0 < t < duration],
                *[
                    float(item)
                    for item in params.get("decupage_boundaries") or []
                    if 0 < float(item) < duration
                ],
                round(duration, 6),
            }
        )
        jumps = {
            round(float(item), 6)
            for item in params.get("decupage_jumps") or []
            if 0 < float(item) < duration
        }
        minimum = max(0.1, min_scene_len_sec)
        merged = [0.0]
        for value in boundaries:
            if value <= 0 or value >= duration:
                continue
            if value - merged[-1] >= minimum:
                merged.append(value)
        if duration - merged[-1] < minimum and len(merged) > 1:
            merged.pop()
        merged.append(duration)
        spans = [
            (merged[index], merged[index + 1])
            for index in range(len(merged) - 1)
        ]
        if not spans:
            spans = [(0.0, duration)]
        report("sampling scenes", 45)
        visuals = _scene_visuals(
            proxy,
            spans,
            topology=topology,
            max_frames=visual_max_frames,
        )
        report("extracting keyframes", 70)
        paths = _scene_keyframes(source, spans, work_dir / "keyframes", size=keyframe_size)
        if len(paths) != len(spans) or any(not item for item in paths):
            raise HandlerError(
                f"scene_analyze produced {sum(1 for item in paths if item)}/"
                f"{len(spans)} keyframes"
            )
        report("writing manifest", 90)
        scenes: list[dict[str, Any]] = []
        previous: str | None = None
        for index, ((start, end), visual) in enumerate(zip(spans, visuals, strict=False)):
            layout = _scene_layout(visual, width, height, topology)
            face = None
            if visual["face_count"] >= 1 and None not in (
                visual["face_cx"],
                visual["face_cy"],
                visual["face_w"],
                visual["face_h"],
            ):
                face = {
                    "cx": min(1.0, max(0.0, float(visual["face_cx"]))),
                    "cy": min(1.0, max(0.0, float(visual["face_cy"]))),
                    "w": min(1.0, max(0.001, float(visual["face_w"]))),
                    "h": min(1.0, max(0.001, float(visual["face_h"]))),
                }
            scenes.append(
                {
                    "scene_id": f"SC_{index + 1:04d}",
                    "start_sample": max(0, round(start * sample_rate)),
                    "end_sample": max(1, round(min(end, duration) * sample_rate)),
                    "start_sec": round(start, 6),
                    "end_sec": round(end, 6),
                    "transition_source": "DECUPAGEM_JUMP"
                    if round(start, 6) in jumps
                    else "VISUAL_CUT",
                    "layout_type": layout,
                    "face_count": int(visual["face_count"]),
                    "face_bbox_norm": face,
                    "face_area_ratio": min(1.0, max(0.0, visual["face_area_ratio"])),
                    "edge_density": min(1.0, max(0.0, visual["edge_density"])),
                    "sharpness_laplacian": max(0.0, visual["sharpness_laplacian"]),
                    "keyframe_path": paths[index] if index < len(paths) else "",
                    "editing_hints": _scene_hints(
                        layout, end - start, visual, previous
                    ),
                }
            )
            previous = layout
        manifest = {
            "schema_version": 1,
            "video_id": str(params.get("video_id") or ""),
            "source_topology": topology,
            "resolution": {"w": width, "h": height},
            "fps_num": int(params.get("fps_num") or round(fps)),
            "fps_den": int(params.get("fps_den") or 1),
            "scenes": scenes,
        }
        target = work_dir / "scenes_manifest.json"
        target.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        archive = work_dir / "scene_keyframes.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for directory, _dirs, files in os.walk(work_dir / "keyframes"):
                for name in files:
                    path = Path(directory) / name
                    bundle.write(path, path.relative_to(work_dir).as_posix())
        shutil.rmtree(work_dir / "keyframes", ignore_errors=True)
        proxy.unlink(missing_ok=True)
        return [target, archive]

    return handler
