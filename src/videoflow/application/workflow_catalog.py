"""Workflow Markdown catalog with seeds and workspace sync."""

from __future__ import annotations

import hashlib
import re
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from videoflow.application.settings import load_settings
from videoflow.domain.errors import StyleError, StyleNotFoundError
from videoflow.domain.workflows import WorkflowDefinition
from videoflow.runtime import portable_home

_LOCK = threading.RLock()
_CACHE: dict[str, tuple[tuple[object, ...], dict[str, WorkflowDefinition]]] = {}
_SEPARATOR = re.compile(r"^---\s*$", re.MULTILINE)


def workflows_dir() -> Path:
    configured = load_settings().presets.workflow_dir.strip()
    return Path(configured).expanduser() if configured else portable_home() / "workflows"


def seed_workflows_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "workflows"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise StyleError("workflow Markdown must start with YAML frontmatter")
    parts = _SEPARATOR.split(text, maxsplit=2)
    if len(parts) < 3:
        raise StyleError("workflow Markdown frontmatter is not closed")
    try:
        payload = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise StyleError(f"invalid workflow frontmatter: {exc}") from exc
    if not isinstance(payload, dict):
        raise StyleError("workflow frontmatter must be a mapping")
    return payload, parts[2].lstrip("\n")


def parse_workflow_markdown(text: str, *, fallback_id: str = "") -> WorkflowDefinition:
    data, body = _frontmatter(text)
    if fallback_id and not data.get("workflow_id"):
        data["workflow_id"] = fallback_id
    data["body"] = body
    try:
        return WorkflowDefinition.model_validate(data)
    except ValueError as exc:
        raise StyleError(f"invalid workflow definition: {exc}") from exc


def render_workflow_markdown(workflow: WorkflowDefinition) -> str:
    payload = workflow.model_dump(mode="json", exclude={"body"})
    payload["updated_at"] = workflow.updated_at or _now()
    header = yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    body = workflow.body.strip()
    return f"---\n{header}\n---\n\n{body}\n"


def _read(path: Path) -> WorkflowDefinition:
    try:
        return parse_workflow_markdown(path.read_text(encoding="utf-8"), fallback_id=path.stem)
    except OSError as exc:
        raise StyleError(f"cannot read workflow {path.name}: {exc}") from exc


def _signature(root: Path) -> tuple[tuple[str, int, int], ...]:
    if not root.is_dir():
        return ()
    return tuple(
        sorted(
            (path.name, path.stat().st_mtime_ns, path.stat().st_size)
            for path in root.glob("*.md")
            if path.is_file()
        )
    )


class WorkflowCatalog:
    def __init__(self, root: Path | None = None, *, include_seeds: bool = True) -> None:
        self.root = Path(root).expanduser() if root is not None else workflows_dir()
        self.include_seeds = include_seeds

    def _roots(self) -> list[Path]:
        roots = [self.root]
        if self.include_seeds:
            roots.append(seed_workflows_dir())
        return roots

    def _workflows(self) -> dict[str, WorkflowDefinition]:
        key = str(self.root.resolve())
        signature = tuple((str(root), _signature(root)) for root in self._roots())
        with _LOCK:
            cached = _CACHE.get(key)
            if cached is not None and cached[0] == signature:
                return dict(cached[1])
        workflows: dict[str, WorkflowDefinition] = {}
        for root in reversed(self._roots()):
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.md")):
                workflow = _read(path)
                workflows[workflow.workflow_id] = workflow
        with _LOCK:
            _CACHE[key] = (signature, dict(workflows))
        return workflows

    def list_workflows(self) -> list[WorkflowDefinition]:
        return [self._workflows()[key] for key in sorted(self._workflows())]

    def list_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "workflow_id": item.workflow_id,
                "name": item.name,
                "description": item.description,
                "aspect_ratio": item.aspect_ratio,
                "platforms": list(item.platforms),
                "steps": len(item.steps),
                "file_path": str(self.path_for(item.workflow_id)),
                "updated_at": item.updated_at,
            }
            for item in self.list_workflows()
        ]

    def get(self, workflow_id: str) -> WorkflowDefinition:
        workflow = self._workflows().get(workflow_id)
        if workflow is None:
            raise StyleNotFoundError(f"workflow not found: {workflow_id}")
        return workflow

    def path_for(self, workflow_id: str) -> Path:
        user = self.root / f"{workflow_id}.md"
        if user.is_file():
            return user
        seed = seed_workflows_dir() / f"{workflow_id}.md"
        return seed if seed.is_file() else user

    def save(self, workflow: WorkflowDefinition, *, overwrite: bool = True) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{workflow.workflow_id}.md"
        if path.exists() and not overwrite:
            raise StyleError(f"workflow already exists: {workflow.workflow_id}")
        workflow = workflow.model_copy(update={"updated_at": _now()})
        path.write_text(render_workflow_markdown(workflow), encoding="utf-8")
        self._invalidate()
        return path

    def delete(self, workflow_id: str) -> bool:
        path = self.root / f"{workflow_id}.md"
        if not path.is_file():
            return False
        path.unlink()
        self._invalidate()
        return True

    def duplicate(self, workflow_id: str, new_id: str, *, name: str = "") -> Path:
        workflow = self.get(workflow_id)
        candidate = workflow.model_copy(
            update={
                "workflow_id": new_id,
                "name": name or f"{workflow.name} (cópia)",
                "version": 1,
            }
        )
        return self.save(candidate, overwrite=False)

    def restore_seed(self, workflow_id: str) -> Path:
        seed = seed_workflows_dir() / f"{workflow_id}.md"
        if not seed.is_file():
            raise StyleNotFoundError(f"workflow seed not found: {workflow_id}")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / seed.name
        shutil.copy2(seed, path)
        self._invalidate()
        return path

    def sync(
        self,
        workspace_dir: str | Path,
        *,
        overwrite: bool = False,
        workflow_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        target = Path(workspace_dir).expanduser() / ".opencode" / "workflows"
        target.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        skipped: list[str] = []
        selected = set(workflow_ids or [])
        for workflow in self.list_workflows():
            if selected and workflow.workflow_id not in selected:
                continue
            destination = target / f"{workflow.workflow_id}.md"
            if destination.exists() and not overwrite:
                skipped.append(str(destination))
                continue
            if not destination.exists() or destination.read_text(
                encoding="utf-8", errors="replace"
            ) != render_workflow_markdown(workflow):
                destination.write_text(render_workflow_markdown(workflow), encoding="utf-8")
            copied.append(str(destination))
        return {"target": str(target), "copied": copied, "skipped": skipped}

    def _invalidate(self) -> None:
        key = str(self.root.resolve())
        with _LOCK:
            _CACHE.pop(key, None)


def catalog() -> WorkflowCatalog:
    return WorkflowCatalog()


def workflow_id_from_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower()).strip("-")
    return slug or "workflow-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


__all__ = [
    "WorkflowCatalog",
    "catalog",
    "parse_workflow_markdown",
    "render_workflow_markdown",
    "seed_workflows_dir",
    "workflow_id_from_name",
    "workflows_dir",
]
