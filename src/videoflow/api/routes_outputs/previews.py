"""Preview creation, status, cancellation, frames and preview downloads."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405
from .common import _frame_source, _frame_target, _timeline_state_path, fail
from .deps import *
from .models import *


def register_preview_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register previews routes."""

    @app.post("/api/v1/jobs/{job_id}/preview")
    def create_preview(
        job_id: str, force: bool = False, background: bool = False
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded":
            raise StateNotReadyError("The job must succeed before preview rendering.")
        preview = job.output / "preview" / "preview.mp4"
        if background:
            state = previews.start(job)
            return {
                "ok": True,
                "status": state.to_dict(),
                "url": f"/api/v1/jobs/{job_id}/preview/file",
            }
        if not force and previews.is_ready(job):
            return {
                "ok": True,
                "status": "ready",
                "path": str(preview),
                "url": f"/api/v1/jobs/{job_id}/preview/file",
            }
        build_preview(job)
        write_preview_manifest(job)
        return {
            "ok": True,
            "status": "ready",
            "path": str(preview),
            "url": f"/api/v1/jobs/{job_id}/preview/file",
        }

    @app.get("/api/v1/jobs/{job_id}/preview/status")
    def preview_status(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        state = previews.get(job_id)
        ready = previews.is_ready(job)
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
            payload["status"] = "stale"
            payload["percent"] = 0
            payload["message"] = "Preview is stale"
        return payload

    @app.post("/api/v1/jobs/{job_id}/preview/cancel")
    def cancel_preview(job_id: str) -> dict[str, object]:
        state = previews.cancel(job_id)
        if state is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "preview_not_found", "message": job_id},
            )
        return {"ok": True, "status": state.to_dict()}

    @app.get("/api/v1/jobs/{job_id}/frames")
    def job_frames(
        job_id: str,
        response: Response,
        start: float = 0.0,
        count: int = 3,
        fps: float = 2.0,
        height: int | None = None,
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
            state_path = _timeline_state_path(job)
            if not state_path.is_file():
                raise StateNotReadyError("The job has no project_state.json timeline.")
            state = load_state(state_path)
            if state.media_info is None:
                raise StateNotReadyError("The project has no media info.")
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "frame_invalid", "message": str(exc)},
            ) from exc
        if height is None:
            height = int(load_settings().quality.proxy_height)
        height = max(64, min(2160, int(height)))
        preview = (
            preview_paths(job)[1] if previews.is_ready(job) else None
        )
        count = max(1, min(12, int(count)))
        step = 1.0 / max(1.0, min(30.0, float(fps)))
        frames: list[dict[str, object]] = []
        hits = 0
        revision = state.revision
        for index in range(count):
            moment = max(0.0, start + index * step)
            target = _frame_target(job, revision, moment, height)
            cached = target.is_file()
            if cached:
                hits += 1
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    source, source_time = _frame_source(state, moment, preview)
                    FFmpegAdapter().render_thumbnail(
                        source,
                        target,
                        time_sec=int(source_time * 10) / 10,
                        height=height,
                    )
                except VideoFlowError as exc:
                    fail(exc)
                    raise
                except Exception as exc:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "ok": False,
                            "code": "frame_failed",
                            "message": str(exc),
                        },
                    ) from exc
            frames.append(
                {
                    "time": round(moment, 3),
                    "url": (
                        f"/api/v1/jobs/{job_id}/frame?time={moment:.3f}"
                        f"&height={height}"
                    ),
                    "cached": cached,
                }
            )
        response.headers["X-Frame-Cache"] = f"{hits}/{count}"
        return {
            "ok": True,
            "revision": revision,
            "height": height,
            "frames": frames,
        }

    @app.get("/api/v1/jobs/{job_id}/frame")
    def job_frame(job_id: str, time: float = 0.0, height: int | None = None) -> FileResponse:
        try:
            job = jobs.get(job_id)
            state_path = _timeline_state_path(job)
            if not state_path.is_file():
                raise StateNotReadyError("The job has no project_state.json timeline.")
            state = load_state(state_path)
            if state.media_info is None:
                raise StateNotReadyError("The project has no media info.")
        except VideoFlowError as exc:
            fail(exc)
            raise
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "frame_invalid", "message": str(exc)},
            ) from exc
        if height is None:
            height = int(load_settings().quality.proxy_height)
        height = max(64, min(2160, int(height)))
        preview = (
            preview_paths(job)[1] if previews.is_ready(job) else None
        )
        target = _frame_target(job, state.revision, time, height)
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                moment = int(max(0.0, min(time, 24 * 3600)) * 10) / 10
                source, source_time = _frame_source(state, moment, preview)
                FFmpegAdapter().render_thumbnail(
                    source, target, time_sec=int(source_time * 10) / 10, height=height
                )
            except VideoFlowError as exc:
                fail(exc)
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=422,
                    detail={"ok": False, "code": "frame_failed", "message": str(exc)},
                ) from exc
        return FileResponse(target, media_type="image/jpeg", filename=target.name)

    @app.get("/api/v1/jobs/{job_id}/preview/file")
    def download_preview(job_id: str) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        preview = job.output / "preview" / "preview.mp4"
        if not previews.is_ready(job):
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "preview_not_found"},
            )
        return FileResponse(preview, media_type="video/mp4", filename="preview.mp4")
