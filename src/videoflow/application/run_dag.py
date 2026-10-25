"""Run DAG, step timing, retry policy, and percentile comparison."""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import median
from typing import Any


def _duration_ms(job: Any) -> int | None:
    if not job.started_at:
        return None
    try:
        start = datetime.fromisoformat(job.started_at)
        end = datetime.fromisoformat(job.finished_at) if job.finished_at else datetime.now(UTC)
    except ValueError:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percentile / 100) * (len(ordered) - 1))))
    return ordered[index]


def build_run_dag(job: Any, recent: list[Any] | None = None) -> dict[str, Any]:
    recipe = (job.options or {}).get("recipe") or {}
    steps = [step for step in recipe.get("steps", []) if isinstance(step, dict)]
    stages = {str(item.get("id")): item for item in job.telemetry.stages()}
    recipe_id = str(recipe.get("id") or (job.result or {}).get("recipe_id") or "")

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for step in steps:
        step_id = str(step.get("id"))
        stage = stages.get(step_id, {})
        status = str(stage.get("status") or "pending")
        if not step.get("enabled", True):
            status = "disabled"
        nodes.append(
            {
                "id": step_id,
                "label": str(stage.get("label") or step.get("type") or step_id),
                "type": str(step.get("type") or ""),
                "needs": [str(item) for item in step.get("needs", [])],
                "status": status,
                "progress": int(stage.get("progress") or 0),
                "duration_ms": stage.get("duration_ms"),
                "started_at": stage.get("started_at"),
                "finished_at": stage.get("finished_at"),
                "message": str(stage.get("message") or ""),
                "error": stage.get("error"),
            }
        )
        for need in step.get("needs", []):
            edges.append({"from": str(need), "to": step_id})

    durations = [
        float(_duration_ms(item))  # type: ignore[arg-type]
        for item in (recent or [])
        if item.status == "succeeded"
        and _duration_ms(item) is not None
        and str((item.options or {}).get("recipe", {}).get("id") or "") == recipe_id
    ]
    previous = next(
        (
            item
            for item in (recent or [])
            if str(item.job_id) != str(job.job_id)
            and item.status == "succeeded"
            and str((item.options or {}).get("recipe", {}).get("id") or "") == recipe_id
        ),
        None,
    )
    return {
        "ok": True,
        "job_id": str(job.job_id),
        "recipe_id": recipe_id,
        "status": job.status,
        "attempts": job.attempts,
        "nodes": nodes,
        "edges": edges,
        "timing": {
            "duration_ms": _duration_ms(job),
            "p50_ms": round(median(durations)) if durations else 0,
            "p95_ms": round(_percentile(durations, 95)),
            "samples": len(durations),
        },
        "retry": {
            "max_attempts": int((job.options or {}).get("max_attempts", 1) or 1),
            "backoff_seconds": float(
                (job.options or {}).get("retry_backoff_seconds", 5) or 0
            ),
        },
        "previous": (
            {
                "job_id": str(previous.job_id),
                "duration_ms": _duration_ms(previous),
                "created_at": previous.created_at,
            }
            if previous is not None
            else None
        ),
    }
