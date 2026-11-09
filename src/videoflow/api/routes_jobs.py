"""Job lifecycle, query, event, and log routes."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from videoflow.application.jobs import TERMINAL, Job, JobManager
from videoflow.domain.errors import StateNotReadyError, VideoFlowError


class VariantSelectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PriorityRequest(BaseModel):
    priority: int = Field(ge=-100, le=100)




class ResumeRequest(BaseModel):
    approved: bool = True
    comment: str = Field(default="", max_length=4000)


def _job_event_stream(job: Job) -> Iterator[str]:
    last: tuple[object, ...] | None = None
    while True:
        payload = job.to_dict()
        marker = (payload["status"], payload["progress"], payload["stage"])
        if marker != last:
            last = marker
            yield f"data: {json.dumps(payload)}\n\n"
        if str(payload["status"]) in TERMINAL:
            break
        time.sleep(0.2)


def register_job_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register the job lifecycle, query, event, and log routes."""


    @app.get("/api/v1/jobs")
    def list_jobs(
        limit: int | None = None, offset: int = 0, summary: bool = False
    ) -> dict[str, object]:
        all_jobs = jobs.list()
        start = max(0, int(offset))
        selected = (
            all_jobs[start:]
            if limit is None
            else all_jobs[start : start + max(0, int(limit))]
        )
        return {
            "ok": True,
            "jobs": [job.to_dict(summary=summary) for job in selected],
            "total": len(all_jobs),
        }

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return {"ok": True, "job": jobs.get(job_id).to_dict()}
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc

    @app.post("/api/v1/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, force: bool = False) -> dict[str, object]:
        try:
            return {
                "ok": True,
                "job": jobs.cancel(job_id, force=force).to_dict(),
            }
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc

    @app.post("/api/v1/jobs/cancel_all")
    def cancel_all_jobs(force: bool = True) -> dict[str, object]:
        return {
            "ok": True,
            "jobs": [job.to_dict() for job in jobs.cancel_all(force=force)],
        }

    @app.delete("/api/v1/jobs/{job_id}")
    def remove_job(job_id: str, force: bool = False) -> dict[str, object]:
        try:
            jobs.remove(job_id, force=force)
            return {"ok": True, "removed": job_id}
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc

    @app.post("/api/v1/jobs/{job_id}/pause")
    def pause_job(job_id: str) -> dict[str, object]:
        return {"ok": True, "job": jobs.pause(job_id).to_dict()}

    @app.post("/api/v1/jobs/{job_id}/unpause")
    def unpause_job(job_id: str) -> dict[str, object]:
        return {"ok": True, "job": jobs.unpause(job_id).to_dict()}

    @app.patch("/api/v1/jobs/{job_id}/priority")
    def set_job_priority(job_id: str, request: PriorityRequest) -> dict[str, object]:
        return {"ok": True, "job": jobs.set_priority(job_id, request.priority).to_dict()}

    @app.post("/api/v1/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status not in {"failed", "cancelled"}:
            raise StateNotReadyError("Only failed or cancelled jobs can be retried.")
        retried = jobs.start(
            job.source,
            job.output,
            {**job.options, "resume": True},
            queue=True,
        )
        return {"ok": True, "job": retried.to_dict()}

    @app.post("/api/v1/jobs/{job_id}/resume", status_code=202)
    def resume_job(job_id: str, request: ResumeRequest) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "waiting_approval":
            raise StateNotReadyError("The job is not waiting for approval.")
        interaction = (job.error or {}).get("interaction")
        if isinstance(interaction, dict) and interaction.get("interaction_id"):
            from videoflow.application import hilt

            interaction_id = str(interaction["interaction_id"])
            hilt.respond(
                job.output,
                job_id,
                interaction_id,
                action="approve" if request.approved else "reject",
                comment=request.comment,
                channel="local",
            )
            resumed = jobs.start(
                job.source,
                job.output,
                {**job.options, "resume": True},
                queue=True,
            )
            hilt.mark_resumed(job.output, interaction_id, str(resumed.job_id))
            jobs.mark_answered(job_id, str(resumed.job_id))
            return {
                "ok": True,
                "job": resumed.to_dict(),
                "gate": str(interaction.get("gate_id") or "review"),
            }
        gate = str((job.error or {}).get("gate_id") or "review")
        approvals = job.output / "approvals"
        approvals.mkdir(parents=True, exist_ok=True)
        (approvals / f"{gate}.json").write_text(
            json.dumps(
                {
                    "approved": request.approved,
                    "comment": request.comment,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        resumed = jobs.start(
            job.source,
            job.output,
            {**job.options, "resume": True},
            queue=True,
        )
        return {"ok": True, "job": resumed.to_dict(), "gate": gate}

    @app.get("/api/v1/jobs/{job_id}/events")
    def job_events(job_id: str) -> StreamingResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc

        return StreamingResponse(
            _job_event_stream(job),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/api/v1/jobs/{job_id}/variants")
    def job_variants(job_id: str) -> dict[str, object]:
        from videoflow.application.variants import compare_variants

        job = jobs.get(job_id)
        return compare_variants(job.output, job.result)

    @app.post("/api/v1/jobs/{job_id}/variants/select")
    def job_variant_winner(
        job_id: str, request: VariantSelectRequest
    ) -> dict[str, object]:
        from videoflow.application.variants import select_variant

        job = jobs.get(job_id)
        payload = select_variant(job.output, request.name)
        return {"ok": True, "winner": payload["selected"]}

    @app.get("/api/v1/jobs/{job_id}/dag")
    def job_dag(job_id: str) -> dict[str, object]:
        from videoflow.application.run_dag import build_run_dag

        job = jobs.get(job_id)
        return build_run_dag(job, jobs.list(limit=60))

    @app.get("/api/v1/jobs/{job_id}/logs")
    def job_logs(
        job_id: str,
        module: str | None = None,
        level: str | None = None,
        limit: int = 500,
        download: bool = False,
    ) -> object:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        rows = job.telemetry.logs(
            module=module,
            level=level,
            limit=max(1, min(1000, limit)),
        )
        if download:
            body = "\n".join(
                f"{row['timestamp']} {row['level'].upper():7} {row['module']}: {row['message']}"
                for row in rows
            )
            suffix = f"-{module}" if module else ""
            return PlainTextResponse(
                body + ("\n" if body else ""),
                headers={
                    "Content-Disposition": f'attachment; filename="videoflow-{job_id}{suffix}.log"'
                },
            )
        return {
            "ok": True,
            "logs": rows,
            "count": len(rows),
            "total": job.telemetry.log_count(),
        }
