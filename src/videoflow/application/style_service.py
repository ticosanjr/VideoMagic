"""Shared style catalog operations for MCP, REST, and the CLI."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from videoflow.application.style_catalog import (
    StyleCatalog,
    parse_style_markdown,
    render_style_markdown,
)
from videoflow.domain.errors import StyleError, StyleNotFoundError
from videoflow.domain.styles import StyleDefinition


def list_styles(catalog: StyleCatalog | None = None) -> list[dict[str, Any]]:
    return (catalog or StyleCatalog()).list_payload()


def get_style(style_id: str, catalog: StyleCatalog | None = None) -> dict[str, Any]:
    active = catalog or StyleCatalog()
    style = active.get(style_id)
    return {
        "ok": True,
        "style": style.model_dump(mode="json"),
        "markdown": render_style_markdown(style),
        "file": str(active.path_for(style.style_id)),
    }


def save_style(
    *,
    style_id: str = "",
    name: str = "",
    markdown_content: str = "",
    updates: Mapping[str, Any] | None = None,
    overwrite: bool = True,
    workspace_dir: str | Path | None = None,
    catalog: StyleCatalog | None = None,
) -> dict[str, Any]:
    active = catalog or StyleCatalog()
    if markdown_content.strip():
        style = parse_style_markdown(
            markdown_content,
            fallback_id=style_id or "style",
        )
        if style_id:
            style = style.model_copy(update={"style_id": style_id})
    else:
        if not style_id:
            raise ValueError("style_id is required")
        try:
            style = active.get(style_id)
        except StyleNotFoundError:
            try:
                style = StyleDefinition(style_id=style_id, name=name or style_id)
            except ValueError as exc:
                raise StyleError(f"invalid style: {exc}") from exc
    if name:
        style = style.model_copy(update={"name": name})
    payload = {key: value for key, value in dict(updates or {}).items() if value is not None}
    if payload:
        style = style.model_copy(update=payload)
    try:
        style = StyleDefinition.model_validate(style.model_dump(mode="json"))
    except ValueError as exc:
        raise StyleError(f"invalid style: {exc}") from exc
    path = active.save(style, overwrite=overwrite)
    sync = active.sync(workspace_dir) if workspace_dir else {}
    return {
        "ok": True,
        "style_id": style.style_id,
        "style": style.model_dump(mode="json"),
        "markdown": render_style_markdown(style),
        "file": str(path),
        "sync": sync,
    }


def learn_style(
    style_id: str,
    notes: list[str],
    *,
    mode: str = "merge",
    max_rules: int = 15,
    workspace_dir: str | Path | None = None,
    catalog: StyleCatalog | None = None,
) -> dict[str, Any]:
    active = catalog or StyleCatalog()
    style = active.learn_rule(style_id, notes, mode=mode, max_rules=max_rules)
    sync = active.sync(workspace_dir) if workspace_dir else {}
    return {
        "ok": True,
        "style_id": style.style_id,
        "rules": [rule.model_dump(mode="json") for rule in style.learned_rules],
        "count": len(style.learned_rules),
        "file": str(active.path_for(style.style_id)),
        "sync": sync,
    }


def sync_styles(
    workspace_dir: str | Path,
    *,
    overwrite: bool = False,
    catalog: StyleCatalog | None = None,
) -> dict[str, Any]:
    active = catalog or StyleCatalog()
    return {"ok": True, "sync": active.sync(workspace_dir, overwrite=overwrite)}


def duplicate_style(
    style_id: str,
    *,
    new_id: str = "",
    name: str = "",
    catalog: StyleCatalog | None = None,
) -> dict[str, Any]:
    from videoflow.application.style_catalog import style_slug

    active = catalog or StyleCatalog()
    target = new_id or style_slug(f"{style_id}-copy")
    path = active.duplicate(style_id, target, name=name)
    return {"ok": True, "style_id": target, "file": str(path)}


def restore_style(style_id: str, catalog: StyleCatalog | None = None) -> dict[str, Any]:
    path = (catalog or StyleCatalog()).restore_seed(style_id)
    return {"ok": True, "style_id": style_id, "file": str(path)}


def delete_style(style_id: str, catalog: StyleCatalog | None = None) -> dict[str, Any]:
    active = catalog or StyleCatalog()
    return {"ok": True, "deleted": active.delete(style_id)}


__all__ = [
    "delete_style",
    "duplicate_style",
    "restore_style",
    "get_style",
    "learn_style",
    "list_styles",
    "save_style",
    "sync_styles",
]
