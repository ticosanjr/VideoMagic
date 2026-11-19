"""Module A orchestration: proxy, detection, visuals, keyframes, cache."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.scene_intel.detect import detect_scene_spans
from videoflow.application.scene_intel.io import write_json
from videoflow.application.scene_intel.manifest import (
    attach_keyframes,
    build_manifest,
    cached_cache_key,
    load_cached_manifest,
    save_manifest,
)
from videoflow.application.scene_intel.proxy import (
    KEYFRAME_SIZE,
    SceneWorkspace,
    cache_key,
    ensure_proxy,
    file_sha256,
    scene_workspace,
)
from videoflow.application.scene_intel.supercontext import build_supercontext
from videoflow.application.scene_intel.visual import analyze_visuals
from videoflow.domain.scenes import ScenesManifest
from videoflow.domain.state import MediaInfo


@dataclass
class SceneAnalysisResult:
    manifest: ScenesManifest
    workspace: SceneWorkspace
    supercontext: dict[str, Any]
    video_id: str
    cache_key: str
    engine: str
    cache_hit: bool
    elapsed_sec: float
    warnings: list[str] = field(default_factory=list)
    keyframes_written: int = 0
    timings: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "source_topology": self.manifest.source_topology,
            "resolution": dict(self.manifest.resolution),
            "scene_count": len(self.manifest.scenes),
            "layout_counts": _layout_counts(self.manifest),
            "engine": self.engine,
            "cache_hit": self.cache_hit,
            "cache_key": self.cache_key,
            "elapsed_sec": round(self.elapsed_sec, 3),
            "warnings": list(self.warnings),
            "manifest_path": str(self.workspace.manifest),
            "supercontext_path": str(self.workspace.supercontext),
            "keyframes_dir": str(self.workspace.keyframes),
            "keyframes_written": self.keyframes_written,
            "timings": dict(self.timings),
        }


def _layout_counts(manifest: ScenesManifest) -> dict[str, int]:
    counts: dict[str, int] = {}
    for scene in manifest.scenes:
        counts[scene.layout_type] = counts.get(scene.layout_type, 0) + 1
    return counts


def resolve_topology(media: MediaInfo, requested: str) -> str:
    if requested in {"dual_canvas", "dual_file", "single_16x9"}:
        return requested
    ratio = media.width / max(1, media.height)
    return "dual_canvas" if abs(ratio - 3.55) < 0.15 else "single_16x9"


def load_scene_cache(
    workspace: SceneWorkspace,
    media: MediaInfo,
    *,
    threshold: float,
    min_scene_len_sec: float,
    topology: str,
    keyframe_size: int,
    decupage_plan: dict[str, Any] | None = None,
    asus: list[dict[str, Any]] | None = None,
    video_id: str = "",
) -> SceneAnalysisResult | None:
    """Return a cached result, refreshing the supercontext for new ASUs."""

    started = time.perf_counter()
    key = cache_key(
        video_sha=video_id or workspace.root.name,
        threshold=threshold,
        min_scene_len_sec=min_scene_len_sec,
        topology=topology,
        keyframe_size=keyframe_size,
    )
    cached = load_cached_manifest(workspace, expected_key=key)
    if cached is None:
        return None
    manifest, metadata = cached
    supercontext = build_supercontext(
        manifest,
        asus=asus,
        decupage_plan=decupage_plan,
        sample_rate=media.audio_sample_rate,
    )
    write_json(workspace.supercontext, supercontext)
    return SceneAnalysisResult(
        manifest=manifest,
        workspace=workspace,
        supercontext=supercontext,
        video_id=video_id or workspace.root.name,
        cache_key=key,
        engine=str(metadata.get("engine") or "cache"),
        cache_hit=True,
        elapsed_sec=time.perf_counter() - started,
        warnings=list(metadata.get("warnings") or []),
        timings={"total": round(time.perf_counter() - started, 4)},
    )


def analyze_scene_project(
    source: Path,
    workspace_root: Path,
    *,
    media: MediaInfo | None = None,
    threshold: float = 3.0,
    min_scene_len_sec: float = 1.5,
    source_topology: str = "auto",
    decupage_plan: dict[str, Any] | None = None,
    asus: list[dict[str, Any]] | None = None,
    force: bool = False,
    keyframe_size: int = KEYFRAME_SIZE,
    video_id: str | None = None,
) -> SceneAnalysisResult:
    """Analyze one video, reusing the SHA-256 cache whenever possible."""

    started = time.perf_counter()
    source_path = Path(source).expanduser()
    if media is None:
        media = FFmpegAdapter().probe(source_path)
    hash_started = time.perf_counter()
    video_id = video_id or file_sha256(source_path)
    hash_sec = time.perf_counter() - hash_started
    topology = resolve_topology(media, source_topology)
    workspace = scene_workspace(workspace_root, video_id)
    key = cache_key(
        video_sha=video_id,
        threshold=threshold,
        min_scene_len_sec=min_scene_len_sec,
        topology=topology,
        keyframe_size=keyframe_size,
    )
    if not force:
        cached = load_scene_cache(
            workspace,
            media,
            threshold=threshold,
            min_scene_len_sec=min_scene_len_sec,
            topology=topology,
            keyframe_size=keyframe_size,
            decupage_plan=decupage_plan,
            asus=asus,
            video_id=video_id,
        )
        if cached is not None:
            return cached
    proxy_started = time.perf_counter()
    proxy, _built = ensure_proxy(source_path, media, workspace, force=force)
    proxy_sec = time.perf_counter() - proxy_started
    duration = media.duration_frames * media.fps_den / max(1, media.fps_num)
    fps = media.fps_num / max(1, media.fps_den)
    detection_started = time.perf_counter()
    detection = detect_scene_spans(
        source_path,
        proxy,
        fps=fps,
        duration=duration,
        threshold=threshold,
        min_scene_len_sec=min_scene_len_sec,
        decupage_plan=decupage_plan,
        sample_rate=media.audio_sample_rate,
    )
    detection_sec = time.perf_counter() - detection_started
    visual_started = time.perf_counter()
    visuals, visual_warnings = analyze_visuals(
        proxy,
        list(detection.spans),
        media,
        source_topology=topology,
    )
    visual_sec = time.perf_counter() - visual_started
    keyframe_started = time.perf_counter()
    # A different cache key (threshold, topology, keyframe size) invalidates
    # the JPEGs together with the manifest.
    keyframes_force = force or cached_cache_key(workspace) != key
    if keyframes_force:
        shutil.rmtree(workspace.keyframes, ignore_errors=True)
    keyframe_paths, keyframe_warnings = attach_keyframes(
        proxy,
        list(detection.spans),
        workspace,
        force=keyframes_force,
        size=keyframe_size,
        fps=fps,
    )
    keyframe_sec = time.perf_counter() - keyframe_started
    warnings = list(detection.warnings) + list(visual_warnings) + list(keyframe_warnings)
    build = build_manifest(
        video_id=video_id,
        media=media,
        spans=list(detection.spans),
        visuals=visuals,
        topology=topology,
        keyframe_paths=keyframe_paths,
        engine=detection.engine,
        warnings=warnings,
    )
    elapsed = time.perf_counter() - started
    save_manifest(
        workspace,
        build.manifest,
        key=key,
        engine=detection.engine,
        warnings=build.warnings,
        elapsed_sec=elapsed,
    )
    supercontext = build_supercontext(
        build.manifest,
        asus=asus,
        decupage_plan=decupage_plan,
        sample_rate=media.audio_sample_rate,
    )
    write_json(workspace.supercontext, supercontext)
    return SceneAnalysisResult(
        manifest=build.manifest,
        workspace=workspace,
        supercontext=supercontext,
        video_id=video_id,
        cache_key=key,
        engine=detection.engine,
        cache_hit=False,
        elapsed_sec=elapsed,
        warnings=warnings,
        keyframes_written=sum(1 for item in keyframe_paths if item),
        timings={
            "hash": round(hash_sec, 4),
            "proxy": round(proxy_sec, 4),
            "detection": round(detection_sec, 4),
            "visual": round(visual_sec, 4),
            "keyframes": round(keyframe_sec, 4),
            "total": round(time.perf_counter() - started, 4),
        },
    )


__all__ = [
    "SceneAnalysisResult",
    "analyze_scene_project",
    "load_scene_cache",
    "resolve_topology",
]
