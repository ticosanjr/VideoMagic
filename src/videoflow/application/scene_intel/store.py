"""Read-side helpers for cached scene manifests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from videoflow.application.scene_intel.io import read_json
from videoflow.application.scene_intel.manifest import cache_metadata_path
from videoflow.application.scene_intel.proxy import SceneWorkspace, scene_workspace
from videoflow.domain.scenes import ScenesManifest


@dataclass
class SceneSnapshot:
    workspace: SceneWorkspace
    manifest: ScenesManifest
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def layout_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for scene in self.manifest.scenes:
            counts[scene.layout_type] = counts.get(scene.layout_type, 0) + 1
        return counts

    def summary(self) -> dict[str, Any]:
        return {
            "video_id": self.manifest.video_id,
            "source_topology": self.manifest.source_topology,
            "resolution": dict(self.manifest.resolution),
            "scene_count": len(self.manifest.scenes),
            "layout_counts": self.layout_counts,
            "engine": self.metadata.get("engine", ""),
            "created_at": self.metadata.get("created_at", ""),
            "elapsed_sec": self.metadata.get("elapsed_sec", 0.0),
            "warnings": list(self.metadata.get("warnings") or []),
            "manifest_path": str(self.workspace.manifest),
            "supercontext_path": str(self.workspace.supercontext),
            "keyframes_dir": str(self.workspace.keyframes),
        }

    def keyframe(self, scene_id: str) -> dict[str, Any] | None:
        scene = next(
            (item for item in self.manifest.scenes if item.scene_id == scene_id),
            None,
        )
        if scene is None:
            return None
        path = Path(scene.keyframe_path) if scene.keyframe_path else None
        exists = bool(path and path.is_file())
        return {
            "scene_id": scene.scene_id,
            "layout_type": scene.layout_type,
            "editing_hints": list(scene.editing_hints),
            "face_bbox_norm": (
                scene.face_bbox_norm.model_dump() if scene.face_bbox_norm else None
            ),
            "start_sec": scene.start_sec,
            "end_sec": scene.end_sec,
            "keyframe_path": str(path) if path else "",
            "exists": exists,
            "bytes": path.stat().st_size if exists and path is not None else 0,
        }

    def cache_status(self) -> dict[str, Any]:
        missing = [
            scene.scene_id
            for scene in self.manifest.scenes
            if scene.keyframe_path and not Path(scene.keyframe_path).is_file()
        ]
        return {
            **self.summary(),
            "cache_key": self.metadata.get("cache_key", ""),
            "cache_version": self.metadata.get("version"),
            "cache_file": str(cache_metadata_path(self.workspace)),
            "keyframe_count": sum(
                1 for scene in self.manifest.scenes if scene.keyframe_path
            ),
            "keyframes_missing": missing,
            "valid": bool(self.metadata) and not missing,
        }


def latest_scene_snapshot(project_output: Path) -> SceneSnapshot | None:
    """Return the newest valid scene manifest under ``<output>/scenes``."""

    root = Path(project_output).expanduser() / "scenes"
    candidates = sorted(
        (path for path in root.glob("*/scenes_manifest.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            manifest = ScenesManifest.model_validate(read_json(path))
        except ValueError:
            continue
        if not manifest.scenes:
            continue
        workspace = scene_workspace(root, path.parent.name)
        return SceneSnapshot(
            workspace=workspace,
            manifest=manifest,
            metadata=read_json(cache_metadata_path(workspace)),
        )
    return None


def snapshot_for_video(project_output: Path, video_id: str) -> SceneSnapshot | None:
    root = Path(project_output).expanduser() / "scenes"
    workspace = scene_workspace(root, video_id)
    if not workspace.manifest.is_file():
        return None
    try:
        manifest = ScenesManifest.model_validate(read_json(workspace.manifest))
    except ValueError:
        return None
    return SceneSnapshot(
        workspace=workspace,
        manifest=manifest,
        metadata=read_json(cache_metadata_path(workspace)),
    )


__all__ = [
    "SceneSnapshot",
    "latest_scene_snapshot",
    "snapshot_for_video",
]
