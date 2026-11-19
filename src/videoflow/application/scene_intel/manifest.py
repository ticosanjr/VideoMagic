"""Build and cache ``scenes_manifest.json``."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from videoflow.application.scene_intel.detect import SceneSpan
from videoflow.application.scene_intel.io import read_json, write_json
from videoflow.application.scene_intel.keyframes import extract_scene_keyframes
from videoflow.application.scene_intel.layout import editing_hints
from videoflow.application.scene_intel.proxy import (
    CACHE_VERSION,
    KEYFRAME_QUALITY,
    KEYFRAME_SIZE,
    SceneWorkspace,
)
from videoflow.application.scene_intel.visual import SceneVisual, classify_layout
from videoflow.domain.scenes import SceneEntry, SceneFaceBox, ScenesManifest
from videoflow.domain.state import MediaInfo


@dataclass
class ManifestBuild:
    manifest: ScenesManifest
    engine: str
    warnings: list[str] = field(default_factory=list)
    keyframes_written: int = 0


def scene_sample_bounds(
    span: SceneSpan,
    *,
    sample_rate: int,
    duration_sec: float,
) -> tuple[int, int]:
    rate = max(1, int(sample_rate))
    start = max(0, round(span.start_sec * rate))
    end = max(start + 1, round(min(span.end_sec, duration_sec) * rate))
    return start, end


def _face_box(visual: SceneVisual) -> SceneFaceBox | None:
    if visual.face_count < 1:
        return None
    if None in (visual.face_cx, visual.face_cy, visual.face_w, visual.face_h):
        return None
    width = min(1.0, max(0.001, float(visual.face_w or 0.0)))
    height = min(1.0, max(0.001, float(visual.face_h or 0.0)))
    cx = min(1.0, max(0.0, float(visual.face_cx or 0.0)))
    cy = min(1.0, max(0.0, float(visual.face_cy or 0.0)))
    return SceneFaceBox(cx=cx, cy=cy, w=width, h=height)


def build_manifest(
    *,
    video_id: str,
    media: MediaInfo,
    spans: list[SceneSpan],
    visuals: list[SceneVisual],
    topology: str,
    keyframe_paths: list[str],
    engine: str,
    warnings: list[str] | None = None,
) -> ManifestBuild:
    duration = media.duration_frames * media.fps_den / max(1, media.fps_num)
    entries: list[SceneEntry] = []
    previous_layout: str | None = None
    for index, span in enumerate(spans):
        visual = visuals[index] if index < len(visuals) else SceneVisual()
        layout = classify_layout(visual, media, topology)
        start_sample, end_sample = scene_sample_bounds(
            span,
            sample_rate=media.audio_sample_rate,
            duration_sec=duration,
        )
        hints = editing_hints(
            layout=layout,
            duration_sec=span.duration,
            edge_density=visual.edge_density,
            sharpness_laplacian=visual.sharpness_laplacian,
            previous_layout=previous_layout,
        )
        entries.append(
            SceneEntry(
                scene_id=f"SC_{index + 1:04d}",
                start_sample=start_sample,
                end_sample=end_sample,
                start_sec=round(span.start_sec, 6),
                end_sec=round(span.end_sec, 6),
                transition_source="DECUPAGEM_JUMP"
                if span.transition_source == "DECUPAGEM_JUMP"
                else "VISUAL_CUT",
                layout_type=layout,
                face_count=visual.face_count,
                face_bbox_norm=_face_box(visual),
                face_area_ratio=min(1.0, max(0.0, visual.face_area_ratio)),
                edge_density=min(1.0, max(0.0, visual.edge_density)),
                sharpness_laplacian=max(0.0, visual.sharpness_laplacian),
                keyframe_path=keyframe_paths[index] if index < len(keyframe_paths) else "",
                editing_hints=hints,
            )
        )
        previous_layout = layout
    manifest = ScenesManifest(
        video_id=video_id,
        source_topology=topology,  # type: ignore[arg-type]
        resolution={"w": media.width, "h": media.height},
        fps_num=media.fps_num,
        fps_den=media.fps_den,
        scenes=entries,
    )
    return ManifestBuild(
        manifest=manifest,
        engine=engine,
        warnings=list(warnings or []),
    )


def cache_metadata_path(workspace: SceneWorkspace) -> Path:
    return workspace.root / "scenes_cache.json"


def cached_cache_key(workspace: SceneWorkspace) -> str:
    return str(read_json(cache_metadata_path(workspace)).get("cache_key") or "")


def load_cached_manifest(
    workspace: SceneWorkspace,
    *,
    expected_key: str,
) -> tuple[ScenesManifest, dict[str, Any]] | None:
    metadata = read_json(cache_metadata_path(workspace))
    if metadata.get("cache_key") != expected_key:
        return None
    if metadata.get("version") != CACHE_VERSION:
        return None
    payload = read_json(workspace.manifest)
    if not payload:
        return None
    try:
        manifest = ScenesManifest.model_validate(payload)
    except ValueError:
        return None
    if not manifest.scenes:
        return None
    for scene in manifest.scenes:
        if scene.keyframe_path and not Path(scene.keyframe_path).is_file():
            return None
    return manifest, metadata


def save_manifest(
    workspace: SceneWorkspace,
    manifest: ScenesManifest,
    *,
    key: str,
    engine: str,
    warnings: list[str],
    elapsed_sec: float,
) -> None:
    write_json(workspace.manifest, manifest.model_dump(mode="json"))
    write_json(
        cache_metadata_path(workspace),
        {
            "version": CACHE_VERSION,
            "cache_key": key,
            "engine": engine,
            "warnings": warnings,
            "elapsed_sec": round(elapsed_sec, 3),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "keyframe_size": KEYFRAME_SIZE,
            "keyframe_quality": KEYFRAME_QUALITY,
            "scene_count": len(manifest.scenes),
        },
    )


def attach_keyframes(
    source: Path,
    spans: list[SceneSpan],
    workspace: SceneWorkspace,
    *,
    force: bool = False,
    size: int = KEYFRAME_SIZE,
    fps: float = 30.0,
) -> tuple[list[str], list[str]]:
    scene_ids = [f"SC_{index + 1:04d}" for index in range(len(spans))]
    return extract_scene_keyframes(
        source,
        spans,
        workspace.keyframes,
        scene_ids=scene_ids,
        size=size,
        fps=fps,
        force=force,
    )


__all__ = [
    "ManifestBuild",
    "attach_keyframes",
    "build_manifest",
    "cache_metadata_path",
    "cached_cache_key",
    "load_cached_manifest",
    "save_manifest",
    "scene_sample_bounds",
]
