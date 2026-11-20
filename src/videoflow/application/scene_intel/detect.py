"""Scene-boundary detection with PySceneDetect and decupage fusion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videoflow.application.video_analysis import detect_scene_changes
from videoflow.domain.errors import IngestError


@dataclass(frozen=True, slots=True)
class SceneSpan:
    start_sec: float
    end_sec: float
    transition_source: str = "VISUAL_CUT"

    @property
    def duration(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)


@dataclass(frozen=True, slots=True)
class DetectionResult:
    spans: tuple[SceneSpan, ...]
    engine: str
    warnings: tuple[str, ...] = ()


def _py_scene_detect(
    proxy: Path,
    *,
    fps: float,
    threshold: float,
    min_scene_len_sec: float,
    frame_skip: int = 0,
) -> list[float]:
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
    manager.detect_scenes(video, show_progress=False, frame_skip=max(0, int(frame_skip)))
    return [
            float(getattr(scene[0], "seconds", 0.0))
            if hasattr(scene[0], "seconds")
            else scene[0].get_seconds()
            for scene in manager.get_scene_list()
        ]


def _ffmpeg_detect(source: Path, *, threshold: float) -> list[float]:
    # FFmpeg is the explicit fallback when PySceneDetect is not installed.
    mapped = max(0.05, min(0.95, float(threshold) / 8.0))
    return detect_scene_changes(source, threshold=mapped)


def decupage_boundaries(
    plan: dict[str, Any] | None,
    *,
    duration: float,
    sample_rate: int,
) -> tuple[set[float], set[float]]:
    if not plan:
        return set(), set()
    boundaries: set[float] = set()
    jumps: set[float] = set()
    cuts = plan.get("cuts")
    if not isinstance(cuts, list):
        return boundaries, jumps
    rate = float(plan.get("sample_rate") or sample_rate or 48_000)
    for cut in cuts:
        if not isinstance(cut, dict):
            continue
        try:
            start = float(cut.get("start_sec", int(cut.get("start_sample", 0)) / rate))
            end = float(cut.get("end_sec", int(cut.get("end_sample", 0)) / rate))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if end - start < 2.0:
            continue
        for value in (start, end):
            if 0 < value < duration:
                boundaries.add(round(value, 6))
                jumps.add(round(value, 6))
    return boundaries, jumps


def detect_scene_spans(
    source: Path,
    proxy: Path,
    *,
    fps: float,
    duration: float,
    threshold: float = 3.0,
    min_scene_len_sec: float = 1.5,
    decupage_plan: dict[str, Any] | None = None,
    sample_rate: int = 48_000,
    proxy_fps: float = 3.0,
) -> DetectionResult:
    """Return ordered scene spans with decupage jump boundaries included."""

    if duration <= 0:
        raise IngestError("Scene analysis needs a positive duration")
    warnings: list[str] = []
    engine = "pyscenedetect"
    try:
        times = _py_scene_detect(
            proxy,
            fps=proxy_fps,
            threshold=threshold,
            min_scene_len_sec=min_scene_len_sec,
            frame_skip=0,
        )
    except Exception as exc:  # noqa: BLE001 - optional dependency
        warnings.append(f"PySceneDetect unavailable; using FFmpeg fallback: {exc}")
        engine = "ffmpeg_fallback"
        times = _ffmpeg_detect(source, threshold=threshold)
    visual = sorted({round(value, 6) for value in times if 0 < value < duration})
    decupage, jumps = decupage_boundaries(
        decupage_plan,
        duration=duration,
        sample_rate=sample_rate,
    )
    boundaries = sorted({0.0, *visual, *decupage})
    minimum = max(0.1, float(min_scene_len_sec))
    # Merge micro-scenes into the following span so coverage stays continuous.
    merged = [0.0]
    for value in boundaries:
        if value <= 0 or value >= duration:
            continue
        if value - merged[-1] >= minimum:
            merged.append(value)
    if duration - merged[-1] < minimum and len(merged) > 1:
        merged.pop()
    merged.append(duration)
    spans: list[SceneSpan] = []
    for index in range(len(merged) - 1):
        start = merged[index]
        end = merged[index + 1]
        transition = "DECUPAGEM_JUMP" if round(start, 6) in jumps else "VISUAL_CUT"
        spans.append(SceneSpan(start, end, transition))
    if not spans:
        spans = [SceneSpan(0.0, duration, "VISUAL_CUT")]
    return DetectionResult(tuple(spans), engine, tuple(warnings))


__all__ = [
    "DetectionResult",
    "SceneSpan",
    "decupage_boundaries",
    "detect_scene_spans",
]
