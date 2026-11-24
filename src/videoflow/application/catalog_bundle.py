from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from videoflow.application.clock import now_iso
from videoflow.application.style_catalog import StyleCatalog, parse_style_markdown
from videoflow.application.workflow_catalog import (
    WorkflowCatalog,
    parse_workflow_markdown,
)
from videoflow.domain.errors import StyleError, VideoFlowError

_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"


class InvalidCatalogBundleError(VideoFlowError):
    code = "invalid_catalog_bundle"


class BundleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80, pattern=_ID_PATTERN)
    markdown_content: str = Field(min_length=1)


class CatalogBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    exported_at: str = ""
    styles: list[BundleEntry] = Field(default_factory=list)
    workflows: list[BundleEntry] = Field(default_factory=list)


def _markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")


def export_catalog_bundle(
    *,
    style_catalog: StyleCatalog | None = None,
    workflow_catalog: WorkflowCatalog | None = None,
) -> CatalogBundle:
    styles = style_catalog or StyleCatalog()
    workflows = workflow_catalog or WorkflowCatalog()
    style_entries = [
        BundleEntry(
            id=item.style_id,
            markdown_content=_markdown(styles.path_for(item.style_id)),
        )
        for item in styles.list_styles()
    ]
    workflow_entries = [
        BundleEntry(
            id=item.workflow_id,
            markdown_content=_markdown(workflows.path_for(item.workflow_id)),
        )
        for item in workflows.list_workflows()
    ]
    return CatalogBundle(
        exported_at=now_iso(),
        styles=sorted(style_entries, key=lambda item: item.id),
        workflows=sorted(workflow_entries, key=lambda item: item.id),
    )


def _payload_dict(payload: dict[str, Any] | str | bytes) -> dict[str, Any]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8-sig")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload.lstrip("\ufeff"))
        except ValueError as exc:
            raise InvalidCatalogBundleError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise InvalidCatalogBundleError("bundle must be a JSON object")
    return payload


def _parsed(entries: list[BundleEntry], kind: str) -> list[Any]:
    parser = parse_style_markdown if kind == "style" else parse_workflow_markdown
    parsed: list[Any] = []
    for entry in entries:
        try:
            item = parser(entry.markdown_content, fallback_id=entry.id)
        except (StyleError, ValueError) as exc:
            raise InvalidCatalogBundleError(f"invalid {kind} {entry.id!r}: {exc}") from exc
        identifier = getattr(item, f"{kind}_id", "")
        if identifier != entry.id:
            raise InvalidCatalogBundleError(
                f"invalid {kind} {entry.id!r}: frontmatter id {identifier!r} "
                "does not match the bundle id"
            )
        parsed.append(item)
    return parsed


def import_catalog_bundle(
    payload: dict[str, Any] | str | bytes,
    *,
    overwrite: bool = True,
    workspace_dir: str = "",
    style_catalog: StyleCatalog | None = None,
    workflow_catalog: WorkflowCatalog | None = None,
) -> dict[str, Any]:
    try:
        bundle = CatalogBundle.model_validate(_payload_dict(payload))
    except ValidationError as exc:
        raise InvalidCatalogBundleError(f"invalid bundle: {exc}") from exc
    if not bundle.styles and not bundle.workflows:
        raise InvalidCatalogBundleError("Bundle contains no styles or workflows")

    styles = style_catalog or StyleCatalog()
    workflows = workflow_catalog or WorkflowCatalog()
    parsed_styles = _parsed(bundle.styles, "style")
    parsed_workflows = _parsed(bundle.workflows, "workflow")
    keys = ("imported_styles", "skipped_styles", "imported_workflows", "skipped_workflows")
    counts = dict.fromkeys(keys, 0)
    for style in parsed_styles:
        if not overwrite and styles.path_for(style.style_id).is_file():
            counts["skipped_styles"] += 1
            continue
        styles.save(style, overwrite=True)
        counts["imported_styles"] += 1
    for workflow in parsed_workflows:
        if not overwrite and workflows.path_for(workflow.workflow_id).is_file():
            counts["skipped_workflows"] += 1
            continue
        workflows.save(workflow, overwrite=True)
        counts["imported_workflows"] += 1
    if workspace_dir:
        styles.sync(workspace_dir, overwrite=overwrite)
        workflows.sync(workspace_dir, overwrite=overwrite)
    return {"ok": True, **counts, "synced": bool(workspace_dir)}


__all__ = [
    "BundleEntry",
    "CatalogBundle",
    "InvalidCatalogBundleError",
    "export_catalog_bundle",
    "import_catalog_bundle",
]
