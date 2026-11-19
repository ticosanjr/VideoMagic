"""Workflow and OpenCode direction-file routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from videoflow.application import workflow_service
from videoflow.application.storage import atomic_write_text
from videoflow.bootstrap import templates_dir
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots


class WorkflowSaveRequest(BaseModel):
    workflow_id: str = ""
    name: str = ""
    description: str = ""
    markdown_content: str = ""
    aspect_ratio: str | None = None
    platforms: list[str] | None = None
    steps: list[dict[str, Any]] | None = None
    approvals: list[str] | None = None
    default_style: str | None = None
    compatible_styles: list[str] | None = None
    export_targets: list[str] | None = None
    body: str | None = None
    workspace_dir: str = ""
    overwrite: bool = True


class WorkflowDuplicateRequest(BaseModel):
    new_id: str = ""
    name: str = ""


class WorkflowSyncRequest(BaseModel):
    workspace_dir: str = Field(min_length=1)
    overwrite: bool = False


class AgentsFileRequest(BaseModel):
    workspace_dir: str = Field(min_length=1)
    content: str = ""


def _workspace(value: str) -> str | None:
    if not value.strip():
        return None
    return str(resolve_allowed(Path(value), allowed_roots()))


def _updates(request: WorkflowSaveRequest) -> dict[str, Any]:
    return {
        key: value
        for key, value in (
            ("description", request.description or None),
            ("aspect_ratio", request.aspect_ratio),
            ("platforms", request.platforms),
            ("steps", request.steps),
            ("approvals", request.approvals),
            ("default_style", request.default_style),
            ("compatible_styles", request.compatible_styles),
            ("export_targets", request.export_targets),
            ("body", request.body),
        )
        if value is not None
    }


def register_workflow_routes(app: FastAPI) -> None:
    @app.get("/api/v1/system/opencode/workflows")
    def workflows_list() -> dict[str, object]:
        return {"ok": True, "workflows": workflow_service.list_workflows()}

    @app.get("/api/v1/system/opencode/workflows/{workflow_id}")
    def workflows_get(workflow_id: str) -> dict[str, object]:
        try:
            return workflow_service.get_workflow(workflow_id)
        except VideoFlowError as exc:
            return exc.to_dict()

    @app.post("/api/v1/system/opencode/workflows", status_code=201)
    def workflows_save(request: WorkflowSaveRequest) -> dict[str, object]:
        try:
            return workflow_service.save_workflow(
                workflow_id=request.workflow_id,
                name=request.name,
                markdown_content=request.markdown_content,
                updates=_updates(request),
                overwrite=request.overwrite,
                workspace_dir=_workspace(request.workspace_dir),
            )
        except (VideoFlowError, ValueError) as exc:
            if isinstance(exc, VideoFlowError):
                return exc.to_dict()
            return {"ok": False, "code": "invalid_workflow", "message": str(exc)}

    @app.delete("/api/v1/system/opencode/workflows/{workflow_id}")
    def workflows_delete(workflow_id: str) -> dict[str, object]:
        return workflow_service.delete_workflow(workflow_id)

    @app.post("/api/v1/system/opencode/workflows/{workflow_id}/duplicate")
    def workflows_duplicate(
        workflow_id: str, request: WorkflowDuplicateRequest
    ) -> dict[str, object]:
        try:
            return workflow_service.duplicate_workflow(
                workflow_id, new_id=request.new_id, name=request.name
            )
        except VideoFlowError as exc:
            return exc.to_dict()

    @app.post("/api/v1/system/opencode/workflows/{workflow_id}/restore")
    def workflows_restore(workflow_id: str) -> dict[str, object]:
        try:
            return workflow_service.restore_workflow(workflow_id)
        except VideoFlowError as exc:
            return exc.to_dict()

    @app.post("/api/v1/system/opencode/workflows/sync")
    def workflows_sync(request: WorkflowSyncRequest) -> dict[str, object]:
        try:
            return workflow_service.sync_workflows(
                _workspace(request.workspace_dir) or "",
                overwrite=request.overwrite,
            )
        except VideoFlowError as exc:
            return exc.to_dict()

    @app.get("/api/v1/system/opencode/agents")
    def agents_get(workspace_dir: str) -> dict[str, object]:
        try:
            target = Path(_workspace(workspace_dir) or "")
            path = target / "AGENTS.md"
            if not path.is_file():
                return {"ok": False, "code": "not_found", "message": str(path)}
            return {"ok": True, "path": str(path), "content": path.read_text(encoding="utf-8")}
        except (OSError, VideoFlowError) as exc:
            return {"ok": False, "code": "agents_failed", "message": str(exc)}

    @app.put("/api/v1/system/opencode/agents")
    def agents_save(request: AgentsFileRequest) -> dict[str, object]:
        try:
            target = Path(_workspace(request.workspace_dir) or "")
            path = target / "AGENTS.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, request.content)
            return {"ok": True, "path": str(path)}
        except (OSError, VideoFlowError) as exc:
            return {"ok": False, "code": "agents_failed", "message": str(exc)}

    @app.post("/api/v1/system/opencode/agents/restore")
    def agents_restore(request: AgentsFileRequest) -> dict[str, object]:
        try:
            target = Path(_workspace(request.workspace_dir) or "")
            template = templates_dir() / "AGENTS.md"
            content = template.read_text(encoding="utf-8")
            path = target / "AGENTS.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, content)
            return {"ok": True, "path": str(path), "content": content}
        except (OSError, VideoFlowError) as exc:
            return {"ok": False, "code": "agents_failed", "message": str(exc)}
