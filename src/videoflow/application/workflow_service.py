"""Shared workflow catalog operations for MCP, REST, and the CLI."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from videoflow.application.workflow_catalog import (
    WorkflowCatalog,
    parse_workflow_markdown,
    render_workflow_markdown,
    workflow_id_from_name,
)
from videoflow.domain.errors import StyleError, StyleNotFoundError
from videoflow.domain.workflows import WorkflowDefinition


def list_workflows(catalog: WorkflowCatalog | None = None) -> list[dict[str, Any]]:
    return (catalog or WorkflowCatalog()).list_payload()


def get_workflow(workflow_id: str, catalog: WorkflowCatalog | None = None) -> dict[str, Any]:
    active = catalog or WorkflowCatalog()
    workflow = active.get(workflow_id)
    return {
        "ok": True,
        "workflow": workflow.model_dump(mode="json"),
        "markdown": render_workflow_markdown(workflow),
        "file": str(active.path_for(workflow.workflow_id)),
    }


def save_workflow(
    *,
    workflow_id: str = "",
    name: str = "",
    markdown_content: str = "",
    updates: Mapping[str, Any] | None = None,
    overwrite: bool = True,
    workspace_dir: str | Path | None = None,
    catalog: WorkflowCatalog | None = None,
) -> dict[str, Any]:
    active = catalog or WorkflowCatalog()
    if markdown_content.strip():
        workflow = parse_workflow_markdown(
            markdown_content,
            fallback_id=workflow_id or "workflow",
        )
        if workflow_id:
            workflow = workflow.model_copy(update={"workflow_id": workflow_id})
    else:
        identifier = workflow_id or workflow_id_from_name(name or "workflow")
        try:
            workflow = active.get(identifier)
        except StyleNotFoundError:
            workflow = WorkflowDefinition(
                workflow_id=identifier,
                name=name or identifier,
            )
    if name:
        workflow = workflow.model_copy(update={"name": name})
    payload = {key: value for key, value in dict(updates or {}).items() if value is not None}
    if payload:
        workflow = workflow.model_copy(update=payload)
    try:
        workflow = WorkflowDefinition.model_validate(workflow.model_dump(mode="json"))
    except ValueError as exc:
        raise StyleError(f"invalid workflow: {exc}") from exc
    path = active.save(workflow, overwrite=overwrite)
    sync = active.sync(workspace_dir) if workspace_dir else {}
    return {
        "ok": True,
        "workflow_id": workflow.workflow_id,
        "workflow": workflow.model_dump(mode="json"),
        "markdown": render_workflow_markdown(workflow),
        "file": str(path),
        "sync": sync,
    }


def duplicate_workflow(
    workflow_id: str,
    *,
    new_id: str = "",
    name: str = "",
    catalog: WorkflowCatalog | None = None,
) -> dict[str, Any]:
    active = catalog or WorkflowCatalog()
    source = active.get(workflow_id)
    target = new_id or workflow_id_from_name(name or f"{workflow_id}-copy")
    path = active.duplicate(workflow_id, target, name=name or f"{source.name} (cópia)")
    return {"ok": True, "workflow_id": target, "file": str(path)}


def restore_workflow(workflow_id: str, catalog: WorkflowCatalog | None = None) -> dict[str, Any]:
    path = (catalog or WorkflowCatalog()).restore_seed(workflow_id)
    return {"ok": True, "workflow_id": workflow_id, "file": str(path)}


def delete_workflow(workflow_id: str, catalog: WorkflowCatalog | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "deleted": (catalog or WorkflowCatalog()).delete(workflow_id),
    }


def sync_workflows(
    workspace_dir: str | Path,
    *,
    overwrite: bool = False,
    catalog: WorkflowCatalog | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "sync": (catalog or WorkflowCatalog()).sync(workspace_dir, overwrite=overwrite),
    }


__all__ = [
    "delete_workflow",
    "duplicate_workflow",
    "get_workflow",
    "list_workflows",
    "restore_workflow",
    "save_workflow",
    "sync_workflows",
]
