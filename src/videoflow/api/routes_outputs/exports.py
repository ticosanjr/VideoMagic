"""Render start, status, cancellation and download."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405
from .common import _frame_source, _frame_target, _timeline_state_path, fail
from .deps import *
from .models import *


def register_export_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register exports routes."""

    @app.post("/api/v1/jobs/{job_id}/render", status_code=202)
    def start_render(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded":
            raise StateNotReadyError("The job must succeed before rendering.")
        state = renders.start(job)
        return {"ok": True, "render": state.to_dict()}

    @app.get("/api/v1/jobs/{job_id}/render/status")
    def render_status(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        state = renders.get(job_id)
        ready = renders.is_ready(job)
        if state is None:
            return {
                "ok": True,
                "status": "ready" if ready else "idle",
                "percent": 100 if ready else 0,
            }
        payload = state.to_dict()
        payload["ok"] = True
        payload["ready"] = ready
        if state.status == "ready" and not ready:
            payload["status"] = "failed"
            payload["percent"] = 0
            payload["message"] = "Render is stale"
            payload["error"] = "The timeline changed during rendering. Render again."
            payload["error_details"] = {
                "ok": False,
                "code": "render_stale",
                "message": "The timeline changed during rendering. Render again.",
            }
        return payload

    @app.post("/api/v1/jobs/{job_id}/render/cancel")
    def cancel_render(job_id: str) -> dict[str, object]:
        state = renders.cancel(job_id)
        if state is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "render_not_found", "message": job_id},
            )
        return {"ok": True, "render": state.to_dict()}

    @app.get("/api/v1/jobs/{job_id}/render/file")
    def download_render(job_id: str) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        path = renders.output_path(job)
        if not renders.is_ready(job):
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "render_not_found", "message": job_id},
            )
        return FileResponse(path, media_type="video/mp4", filename=path.name)
