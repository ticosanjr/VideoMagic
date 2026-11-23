"""Source file, artifact and step-output routes."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405
from .common import _frame_source, _frame_target, _timeline_state_path, fail
from .deps import *
from .models import *


def register_artifact_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register artifact routes."""

    @app.get("/api/v1/jobs/{job_id}/source/file")
    def job_source_file(job_id: str) -> FileResponse:
        job = jobs.get(job_id)
        state = load_state(_timeline_state_path(job))
        media = state.media_info
        if media is None:
            raise StateNotReadyError("The project has no media info.")
        source = resolve_allowed(Path(media.source_path), allowed_roots())
        if not source.is_file():
            raise StateNotReadyError("The source media is not available.")
        return FileResponse(source, media_type="video/mp4", filename=source.name)

    @app.get("/api/v1/jobs/{job_id}/artifacts/{artifact_name}")
    def download_job_artifact(job_id: str, artifact_name: str) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        artifacts = (job.result or {}).get("artifacts") or {}
        raw = artifacts.get(artifact_name) if isinstance(artifacts, dict) else None
        if not raw:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "artifact_not_found", "message": artifact_name},
            )
        path = Path(str(raw)).expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "artifact_not_found", "message": artifact_name},
            )
        return FileResponse(path, filename=path.name)

    @app.patch("/api/v1/jobs/{job_id}/artifacts/{artifact_name}")
    def update_job_artifact(
        job_id: str, artifact_name: str, request: ArtifactUpdateRequest
    ) -> dict[str, object]:
        editable = {
            "motion_scenes": "scenes",
            "motion_callouts": "callouts",
            "storyboard_units": "units",
            "script_json": "sections",
            "style_guide": "",
        }
        if artifact_name not in editable:
            raise HTTPException(
                status_code=422,
                detail={
                    "ok": False,
                    "code": "artifact_not_editable",
                    "message": f"Artifact {artifact_name} is not editable.",
                },
            )
        job = jobs.get(job_id)
        artifacts = (job.result or {}).get("artifacts") or {}
        raw = artifacts.get(artifact_name) if isinstance(artifacts, dict) else None
        if not raw:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "artifact_not_found",
                    "message": artifact_name,
                },
            )
        path = Path(str(raw)).expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "artifact_not_found",
                    "message": artifact_name,
                },
            )
        key = editable[artifact_name]
        if key and not isinstance(request.payload.get(key), list):
            raise HTTPException(
                status_code=422,
                detail={
                    "ok": False,
                    "code": "artifact_invalid",
                    "message": f"Artifact {artifact_name} requires a list at '{key}'.",
                },
            )
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            json.dumps(request.payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        audit = output / "plan-edits.jsonl"
        with audit.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "at": now_iso(),
                        "artifact": artifact_name,
                        "path": str(path),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        return {
            "ok": True,
            "artifact": artifact_name,
            "path": str(path),
            "note": "Plan saved. Re-run the affected step or render to apply it.",
        }

    @app.get("/api/v1/jobs/{job_id}/steps/{step_id}/outputs")
    def job_step_outputs(job_id: str, step_id: str) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        if not step_id or "/" in step_id or "\\" in step_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "ok": False,
                    "code": "step_invalid",
                    "message": "Invalid step id.",
                },
            )
        payload = load_step_outputs(job.output, step_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "step_outputs_missing",
                    "message": f"No outputs persisted for step {step_id}.",
                },
            )
        return {"ok": True, **summarize_step_outputs(payload)}

    @app.get("/api/v1/jobs/{job_id}/steps/{step_id}/outputs/{port_id}")
    def job_step_output_port(
        job_id: str, step_id: str, port_id: str
    ) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        if not step_id or "/" in step_id or "\\" in step_id:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "step_invalid", "message": "Invalid step id."},
            )
        payload = load_step_outputs(job.output, step_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "step_outputs_missing",
                    "message": f"No outputs persisted for step {step_id}.",
                },
            )
        item = step_output_port(payload, port_id)
        if item is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "step_port_missing",
                    "message": f"Step {step_id} has no output port {port_id}.",
                },
            )
        return {"ok": True, "step_id": step_id, "port": item}

    @app.get("/api/v1/jobs/{job_id}/steps/{step_id}/files/{file_name}")
    def job_step_output_file(
        job_id: str, step_id: str, file_name: str
    ) -> FileResponse:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        if not step_id or "/" in step_id or "\\" in step_id:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "step_invalid", "message": "Invalid step id."},
            )
        payload = load_step_outputs(job.output, step_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "step_outputs_missing",
                    "message": f"No outputs persisted for step {step_id}.",
                },
            )
        for item in payload.get("files", []):
            if not isinstance(item, dict) or str(item.get("name")) != file_name:
                continue
            path = Path(str(item.get("path", ""))).expanduser().resolve()
            if path.is_relative_to(job.output.expanduser().resolve()) and path.is_file():
                return FileResponse(path, filename=path.name)
        raise HTTPException(
            status_code=404,
            detail={
                "ok": False,
                "code": "step_file_missing",
                "message": f"Step {step_id} has no file {file_name}.",
            },
        )

    @app.post("/api/v1/jobs/{job_id}/steps/{step_id}/save")
    def save_job_step_outputs(
        job_id: str, step_id: str, request: StepOutputSaveRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if not step_id or "/" in step_id or "\\" in step_id:
            raise RecipeError("Invalid step id.")
        target = resolve_allowed(Path(request.target_dir), allowed_roots())
        saved = save_step_outputs(job.output, step_id, target)
        if not saved:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "step_outputs_missing",
                    "message": f"No outputs persisted for step {step_id}.",
                },
            )
        return {"ok": True, "saved": saved}

    @app.get("/api/v1/jobs/{job_id}/state")
    def job_state(job_id: str) -> dict[str, object]:
        try:
            job = jobs.get(job_id)
        except VideoFlowError as exc:
            raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
        path = (job.output / "project_state.json").expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "state_not_found",
                    "message": "The job has not written a project state yet.",
                },
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=500,
                detail={"ok": False, "code": "state_invalid", "message": str(exc)},
            ) from exc
        return payload if isinstance(payload, dict) else {"state": payload}
