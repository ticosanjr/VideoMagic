"""Review, comments, thumbnails and b-roll routes."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405
from .common import _frame_source, _frame_target, _timeline_state_path, fail
from .deps import *
from .models import *


def register_qa_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register QA routes."""

    @app.get("/api/v1/jobs/{job_id}/review")
    def job_review(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        return {"ok": True, **review_payload(job.output)}

    @app.patch("/api/v1/jobs/{job_id}/review")
    def decide_job_review(
        job_id: str, request: ReviewDecisionRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        approval = approve_review(
            job.output,
            approved=request.approved,
            comment=request.comment,
            reviewer=request.reviewer,
        )
        return {"ok": True, "approval": approval}

    @app.get("/api/v1/jobs/{job_id}/review/comments")
    def job_review_comments(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        return {"ok": True, "comments": list_review_comments(job.output)}

    @app.post("/api/v1/jobs/{job_id}/review/comments", status_code=201)
    def add_job_review_comment(
        job_id: str, request: ReviewCommentRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        comments = add_review_comment(
            job.output,
            author=request.author,
            text=request.text,
            time_sec=request.time_sec,
        )
        return {"ok": True, "comments": comments}

    @app.get("/api/v1/jobs/{job_id}/thumbnails")
    def job_thumbnails(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        return {"ok": True, **list_thumbnails(job.output)}

    @app.get("/api/v1/jobs/{job_id}/clips/{clip_id}/thumbnail")
    def job_clip_thumbnail(job_id: str, clip_id: str) -> FileResponse:
        job = jobs.get(job_id)
        state_path = Path(
            str((job.result or {}).get("state_path") or job.output / "project_state.json")
        )
        state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        clip = next(
            (item for item in state.video_segments if item.clip_id == clip_id), None
        )
        if clip is None or state.media_info is None:
            raise StateNotReadyError(f"Unknown clip: {clip_id}")
        media = state.media_info
        fps = media.fps_num / media.fps_den
        slug = "".join(
            char if char.isalnum() or char in "-_" else "-" for char in clip_id
        )
        target = job.output / "thumbnails" / "clips" / f"{slug}.png"
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            midpoint = (clip.source_in_frame + clip.source_out_frame) / 2
            FFmpegAdapter().render_thumbnail(
                Path(media.source_path),
                target,
                time_sec=max(0.0, midpoint / max(1.0, fps)),
            )
        if not target.is_file():
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "clip_thumbnail_not_found"},
            )
        return FileResponse(target, media_type="image/png", filename=target.name)

    @app.get("/api/v1/jobs/{job_id}/thumbnails/metrics")
    def job_thumbnail_metrics(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        return {"ok": True, "metrics": thumbnail_metrics(job.output)}

    @app.get("/api/v1/jobs/{job_id}/thumbnails/{name}")
    def job_thumbnail_file(job_id: str, name: str) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        directory = (job.output / "thumbnails").resolve()
        path = (directory / name).resolve()
        if path.parent != directory or not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "thumbnail_not_found", "message": name},
            )
        return FileResponse(path, media_type="image/png", filename=path.name)

    @app.post("/api/v1/jobs/{job_id}/thumbnails/{name}/metric")
    def record_job_thumbnail_metric(
        job_id: str, name: str, request: ThumbnailMetricRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        metric = record_thumbnail_metric(
            job.output,
            name,
            impressions=request.impressions,
            clicks=request.clicks,
        )
        return {"ok": True, "metric": metric, "metrics": thumbnail_metrics(job.output)}

    @app.post("/api/v1/jobs/{job_id}/thumbnails/select")
    def choose_job_thumbnail(
        job_id: str, request: ThumbnailSelectRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        payload = select_thumbnail(job.output, request.name)
        return {"ok": True, **payload}

    @app.post("/api/v1/jobs/{job_id}/broll/undo")
    def undo_job_broll(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        approval = undo_approval(job.output)
        return {"ok": True, "approval": approval}

    @app.post("/api/v1/jobs/{job_id}/broll/redo")
    def redo_job_broll(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        approval = redo_approval(job.output)
        return {"ok": True, "approval": approval}

    @app.get("/api/v1/jobs/{job_id}/broll")
    def job_broll(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        plan = (job.result or {}).get("broll_plan", {})
        return {
            "ok": True,
            "plan": plan,
            "approval": load_approvals(job.output),
        }

    @app.patch("/api/v1/jobs/{job_id}/broll")
    def update_job_broll(job_id: str, request: BrollApprovalRequest) -> dict[str, object]:
        job = jobs.get(job_id)
        plan = (job.result or {}).get("broll_plan", {})
        approval = save_approval(
            job.output,
            title=request.title,
            approved=request.approved,
            order=request.order,
            plan=plan,
        )
        return {"ok": True, "approval": approval}
