"""Scene-intelligence MCP tool: manifest, keyframes, supercontext, cache."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.projects import get_project
from videoflow.application.scene_intel.io import read_json
from videoflow.application.scene_intel.store import (
    SceneSnapshot,
    latest_scene_snapshot,
    snapshot_for_video,
)
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.agent_helpers import _job_payload
from videoflow.mcp_server.context import error


def _resolve_snapshot(
    output: Path,
    video_id: str,
) -> SceneSnapshot | None:
    if video_id:
        return snapshot_for_video(output, video_id)
    return latest_scene_snapshot(output)


def register_scene_tools(register: Any, ctx: Any, *, wait_fn: Any) -> None:
    manager = ctx.manager

    @register
    def vf_scenes(
        action: str = "manifest",
        project_id: str = "",
        video_id: str = "",
        video_path: str = "",
        scene_id: str = "",
        decupage_plan_path: str = "",
        source_topology: str = "auto",
        threshold: float = 3.0,
        min_scene_len_sec: float = 1.5,
        keyframe_size: int = 544,
        compute_policy: str = "auto",
        force: bool = False,
        offset: int = 0,
        limit: int = 200,
        wait: bool = True,
        timeout_sec: float = 1800.0,
    ) -> dict[str, Any]:
        """Analyze scenes or read the cached manifest, keyframes, and cache state."""

        try:
            record = get_project(project_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        output = Path(record.output)
        selected = action.strip().lower()
        if selected == "analyze":
            source = Path(
                video_path or record.primary_source or record.output
            ).expanduser()
            params: dict[str, Any] = {
                "video_path": video_path,
                "decupage_plan_path": decupage_plan_path,
                "source_topology": source_topology,
                "threshold": threshold,
                "min_scene_len_sec": min_scene_len_sec,
                "keyframe_size": keyframe_size,
                "compute_policy": compute_policy,
                "force": force,
            }
            job = manager.start(
                source,
                output,
                {
                    "mode": "step",
                    "project_id": record.project_id,
                    "step_type": "scene.analyze",
                    "params": {key: value for key, value in params.items() if value != ""},
                },
                queue=True,
                project_id=record.project_id,
            )
            response: dict[str, Any] = {
                "ok": True,
                "project_id": record.project_id,
                "job": _job_payload(job),
            }
            if wait:
                response["wait"] = wait_fn(
                    manager, record.project_id, str(job.job_id), timeout_sec
                )
                if response["wait"].get("ok"):
                    snapshot = _resolve_snapshot(output, video_id)
                    if snapshot is not None:
                        response["scenes"] = snapshot.summary()
            return response

        snapshot = _resolve_snapshot(output, video_id)
        if snapshot is None:
            return error(
                "scenes_missing",
                "No scene manifest is cached for this project",
                fix_hint=(
                    "Run vf_scenes(action='analyze', project_id=...) after ingest "
                    "or after decupage.snap."
                ),
            )
        if selected == "manifest":
            total = len(snapshot.manifest.scenes)
            start = max(0, int(offset))
            page_size = max(0, int(limit))
            end = total if page_size == 0 else min(total, start + page_size)
            scenes = [
                scene.model_dump(mode="json")
                for scene in snapshot.manifest.scenes[start:end]
            ]
            return {
                "ok": True,
                "project_id": record.project_id,
                "summary": snapshot.summary(),
                "schema_version": snapshot.manifest.schema_version,
                "scenes": scenes,
                "total": total,
                "offset": start,
                "next_offset": end if end < total else None,
                "paths": {
                    "manifest": str(snapshot.workspace.manifest),
                    "supercontext": str(snapshot.workspace.supercontext),
                    "keyframes": str(snapshot.workspace.keyframes),
                },
            }
        if selected == "keyframe":
            if not scene_id:
                return error("scene_id_required", "scene_id is required for action='keyframe'")
            item = snapshot.keyframe(scene_id)
            if item is None:
                return error(
                    "scene_not_found",
                    f"Scene {scene_id} is not in the cached manifest",
                )
            return {
                "ok": True,
                "project_id": record.project_id,
                **item,
                "image_returned": False,
            }
        if selected == "supercontext":
            payload = read_json(snapshot.workspace.supercontext)
            if not payload:
                return error(
                    "supercontext_missing",
                    "timeline_supercontext.json is missing or invalid",
                    fix_hint="Re-run vf_scenes(action='analyze', force=True).",
                )
            return {
                "ok": True,
                "project_id": record.project_id,
                "path": str(snapshot.workspace.supercontext),
                "supercontext": payload,
            }
        if selected == "cache":
            return {
                "ok": True,
                "project_id": record.project_id,
                "cache": snapshot.cache_status(),
            }
        return error(
            "unknown_action",
            "vf_scenes supports analyze, manifest, keyframe, supercontext, or cache",
        )


__all__ = ["register_scene_tools"]
