"""Human-in-the-loop API: inspect, answer, upload, and resume."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from videoflow.application import hilt
from videoflow.application.jobs import JobManager
from videoflow.domain.errors import HiltResponseError, StateNotReadyError, VideoFlowError


class HiltRespondRequest(BaseModel):
    action: Literal["approve", "reject", "submit"] = "submit"
    answers: dict[str, Any] = Field(default_factory=dict)
    comment: str = Field(default="", max_length=8000)
    responder: str = Field(default="local", max_length=200)
    channel: str = Field(default="local", max_length=40)
    token: str = Field(default="", max_length=500)


class BulkApproveItem(BaseModel):
    job_id: str = Field(min_length=1, max_length=120)
    interaction_id: str = Field(min_length=1, max_length=200)


class BulkApproveRequest(BaseModel):
    items: list[BulkApproveItem] = Field(min_length=1, max_length=50)
    comment: str = Field(default="", max_length=4000)


def _waiting_job(jobs: JobManager, job_id: str):
    job = jobs.get(job_id)
    if job.status not in {"waiting_approval", "waiting_input"}:
        raise StateNotReadyError("The job is not waiting for a human response.")
    return job


def _interaction(
    jobs: JobManager, job_id: str, interaction_id: str
) -> tuple[Any, dict[str, object]]:
    job = jobs.get(job_id)
    request = hilt.find_request(job.output, job_id, interaction_id)
    response = hilt.load_response(job.output, interaction_id)
    return job, hilt.public_payload(job.output, request, response)


def register_hilt_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register the human interaction routes for one app instance."""

    @app.get("/api/v1/hilt/pending")
    def hilt_pending() -> dict[str, object]:
        items: list[dict[str, object]] = []
        for job in jobs.list():
            if job.status not in {"waiting_approval", "waiting_input"}:
                continue
            try:
                requests = hilt.pending_for_job(job.output, str(job.job_id))
            except OSError:
                continue
            for request in requests:
                items.append(
                    {
                        "job_id": str(job.job_id),
                        "job_status": job.status,
                        "job_message": job.message,
                        "interaction": hilt.public_payload(job.output, request),
                    }
                )
        return {"ok": True, "interactions": items, "count": len(items)}

    @app.get("/api/v1/jobs/{job_id}/interactions")
    def job_interactions(job_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        items = []
        for request in hilt.list_requests(job.output, job_id=job_id):
            response = hilt.load_response(job.output, request.interaction_id)
            items.append(hilt.public_payload(job.output, request, response))
        return {"ok": True, "interactions": items, "count": len(items)}

    @app.get("/api/v1/jobs/{job_id}/interactions/{interaction_id}")
    def job_interaction(job_id: str, interaction_id: str) -> dict[str, object]:
        _job, payload = _interaction(jobs, job_id, interaction_id)
        return {"ok": True, "interaction": payload}

    @app.post("/api/v1/jobs/{job_id}/interactions/{interaction_id}/respond", status_code=202)
    def respond(
        job_id: str,
        interaction_id: str,
        request: HiltRespondRequest,
    ) -> dict[str, object]:
        job = _waiting_job(jobs, job_id)
        existing = hilt.load_response(job.output, interaction_id)
        if existing is not None and existing.resumed_job_id:
            try:
                resumed_job = jobs.get(existing.resumed_job_id)
            except VideoFlowError:
                resumed_job = None
            if resumed_job is not None:
                return {
                    "ok": True,
                    "job": resumed_job.to_dict(),
                    "resumed_job_id": existing.resumed_job_id,
                    "interaction": hilt.public_payload(
                        job.output,
                        hilt.find_request(job.output, job_id, interaction_id),
                        existing,
                    ),
                }
        _request, response = hilt.respond(
            job.output,
            job_id,
            interaction_id,
            action=request.action,
            answers=request.answers,
            comment=request.comment,
            responder=request.responder,
            channel=request.channel,
            token=request.token,
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
            "resumed_job_id": str(resumed.job_id),
            "action": response.action,
        }

    @app.post(
        "/api/v1/jobs/{job_id}/interactions/{interaction_id}/files",
        status_code=201,
    )
    async def upload_files(
        job_id: str,
        interaction_id: str,
        files: Annotated[list[UploadFile], File()],
        request_id: Annotated[str, Form()] = "",
    ) -> dict[str, object]:
        job = _waiting_job(jobs, job_id)
        hilt.find_request(job.output, job_id, interaction_id)
        uploaded = []
        for upload in files:
            data = await upload.read()
            attachment = hilt.save_attachment(
                job.output,
                interaction_id,
                request_id=request_id,
                filename=upload.filename or "attachment",
                data=data,
                content_type=upload.content_type or "",
            )
            uploaded.append(attachment.model_dump(mode="json"))
        return {"ok": True, "attachments": uploaded}

    @app.post("/api/v1/hilt/approve")
    def bulk_approve(request: BulkApproveRequest) -> dict[str, object]:
        approved: list[dict[str, object]] = []
        failed: list[dict[str, object]] = []
        for item in request.items:
            try:
                job = _waiting_job(jobs, item.job_id)
                hilt.find_request(job.output, item.job_id, item.interaction_id)
                updated, _response = hilt.respond(
                    job.output,
                    item.job_id,
                    item.interaction_id,
                    action="approve",
                    comment=request.comment,
                    responder="bulk",
                )
                resumed = jobs.start(
                    job.source,
                    job.output,
                    {**job.options, "resume": True},
                    queue=True,
                )
                hilt.mark_resumed(
                    job.output, item.interaction_id, str(resumed.job_id)
                )
                jobs.mark_answered(item.job_id, str(resumed.job_id))
                approved.append(
                    {
                        "job_id": item.job_id,
                        "interaction_id": item.interaction_id,
                        "status": updated.status,
                        "resumed_job_id": str(resumed.job_id),
                    }
                )
            except VideoFlowError as exc:
                failed.append(
                    {
                        "job_id": item.job_id,
                        "interaction_id": item.interaction_id,
                        "error": exc.to_dict(),
                    }
                )
        return {"ok": not failed, "approved": approved, "failed": failed}

    @app.post("/api/v1/jobs/{job_id}/interactions/{interaction_id}/cancel")
    def cancel_interaction(job_id: str, interaction_id: str) -> dict[str, object]:
        job = jobs.get(job_id)
        hilt.find_request(job.output, job_id, interaction_id)
        hilt.cancel_request(job.output, interaction_id)
        return {"ok": True, "job": jobs.cancel(job_id).to_dict()}

    @app.get(
        "/api/v1/jobs/{job_id}/interactions/{interaction_id}/artifacts/{artifact_id}"
    )
    def download_artifact(
        job_id: str, interaction_id: str, artifact_id: str
    ) -> FileResponse:
        job = jobs.get(job_id)
        request = hilt.find_request(job.output, job_id, interaction_id)
        artifact = next(
            (item for item in request.artifacts if item.id == artifact_id), None
        )
        if artifact is None:
            raise HiltResponseError(f"Unknown artifact: {artifact_id}")
        path = hilt.resolve_output_path(job.output, artifact.path)
        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "artifact_not_found",
                    "message": f"Artifact is missing: {artifact.label}",
                },
            )
        return FileResponse(path, filename=path.name)
