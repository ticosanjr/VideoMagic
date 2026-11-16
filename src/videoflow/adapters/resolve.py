"""Optional DaVinci Resolve Studio scripting bridge.

The adapter never imports Resolve at module import time. It is capability-detected
at runtime and falls back to the static FCPXML artifact when Resolve is absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.core.context import PipelineContext
from videoflow.domain.errors import RecipeError
from videoflow.steps.base import StepIO
from videoflow.steps.nle_sync import NleSyncParams, NleSyncStep


def _resolve() -> Any:
    try:
        import DaVinciResolveScript as dvr  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on Resolve install
        raise RecipeError(
            "DaVinci Resolve scripting is unavailable. Enable External Scripting "
            "in Resolve Studio and set RESOLVE_SCRIPT_API/RESOLVE_SCRIPT_LIB."
        ) from exc
    resolve = dvr.scriptapp("Resolve")
    if resolve is None:  # pragma: no cover - depends on running Resolve
        raise RecipeError("DaVinci Resolve is not running or scripting is disabled")
    return resolve


def resolve_status() -> dict[str, Any]:
    try:
        resolve = _resolve()
    except RecipeError as exc:
        return {"available": False, "message": exc.message}
    manager = resolve.GetProjectManager()
    project = manager.GetCurrentProject() if manager is not None else None
    return {
        "available": True,
        "product": resolve.GetProductName(),
        "version": resolve.GetVersionString(),
        "project": project.GetName() if project is not None else "",
    }


def resolve_roundtrip(
    context: PipelineContext,
    *,
    direction: str,
    path: str,
    apply: bool,
) -> dict[str, Any]:
    """Push FCPXML into Resolve or pull markers/cuts back into VideoFlow."""

    resolve = _resolve()
    manager = resolve.GetProjectManager()
    if manager is None:
        raise RecipeError("Resolve has no project manager")
    project = manager.GetCurrentProject()
    if project is None:
        raise RecipeError("Resolve has no current project")
    media_pool = project.GetMediaPool()
    if direction == "push":
        if not path:
            raise RecipeError("Resolve push needs an FCPXML path")
        imported = media_pool.ImportTimelineFromFile(
            str(Path(path).expanduser()), {"timelineName": "VideoFlow"}
        )
        if not imported:
            raise RecipeError("Resolve rejected the FCPXML timeline")
        return {
            "ok": True,
            "nle": "resolve",
            "direction": "push",
            "project": project.GetName(),
            "timeline": imported.GetName() if hasattr(imported, "GetName") else "VideoFlow",
        }
    timeline = project.GetCurrentTimeline()
    if timeline is None:
        raise RecipeError("Resolve has no current timeline")
    markers: list[dict[str, Any]] = []
    clips: list[dict[str, Any]] = []
    if hasattr(timeline, "GetMarkers"):
        raw = timeline.GetMarkers() or {}
        for frame, payload in raw.items():
            if isinstance(payload, dict):
                markers.append(
                    {
                        "frame": int(frame),
                        "color": payload.get("color", ""),
                        "name": payload.get("name", ""),
                        "note": payload.get("note", ""),
                        "duration": payload.get("duration", 1),
                    }
                )
    if hasattr(timeline, "GetItemListInTrack"):
        for track_type in ("video", "audio"):
            for track_index in range(1, 9):
                try:
                    items = timeline.GetItemListInTrack(track_type, track_index) or []
                except Exception:  # noqa: BLE001 - Resolve API varies by version
                    items = []
                for item in items:
                    clips.append(
                        {
                            "track": f"{track_type}{track_index}",
                            "name": item.GetName() if hasattr(item, "GetName") else "",
                            "start": item.GetStart() if hasattr(item, "GetStart") else 0,
                            "end": item.GetEnd() if hasattr(item, "GetEnd") else 0,
                        }
                    )
    report = {
        "ok": True,
        "nle": "resolve",
        "direction": direction,
        "project": project.GetName(),
        "timeline": timeline.GetName() if hasattr(timeline, "GetName") else "",
        "markers": markers,
        "clips": clips,
        "applied": False,
    }
    if apply and path:
        step = NleSyncStep()
        step.run(
            context,
            NleSyncParams(format="fcpxml", path=path, apply=True),
            StepIO(stage="resolve.sync_back"),
        )
        report["sync_back"] = context.metadata.get("sync_back_report", {})
        report["applied"] = True
    return report
