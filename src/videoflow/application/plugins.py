"""Local plugin loader for custom steps and integrations."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.plugin_sandbox import check_plugin
from videoflow.application.schema_migrations import migrate_plugin_manifest
from videoflow.runtime import portable_home


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    id: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=120)
    version: str = "0.1.0"
    api_version: int = 1
    entry: str = "plugin.py"
    description: str = ""
    enabled: bool = True
    permissions: list[str] = Field(default_factory=list)
    provides: list[str] = Field(default_factory=list)


def plugins_dir() -> Path:
    return portable_home() / "plugins"


def list_plugins() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    root = plugins_dir()
    for directory in sorted(root.iterdir()) if root.is_dir() else []:
        manifest_path = directory / "plugin.json"
        if not directory.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = PluginManifest.model_validate(
                migrate_plugin_manifest(
                    json.loads(manifest_path.read_text(encoding="utf-8"))
                )
            )
            if manifest.api_version > 1:
                raise ValueError(
                    f"plugin API {manifest.api_version} is newer than 1"
                )
            entry = directory / manifest.entry
            result.append(
                {
                    **manifest.model_dump(mode="json"),
                    "path": str(directory),
                    "entry_exists": entry.is_file(),
                }
            )
        except (OSError, ValueError):
            continue
    return result


def load_plugins() -> list[dict[str, object]]:
    loaded: list[dict[str, object]] = []
    for manifest in list_plugins():
        if not manifest.get("enabled") or not manifest.get("entry_exists"):
            continue
        entry = Path(str(manifest["path"])) / str(manifest["entry"])
        violations = check_plugin(entry, list(manifest.get("permissions") or []))
        if violations:
            loaded.append(
                {
                    **manifest,
                    "loaded": False,
                    "sandbox": violations,
                    "error": "plugin blocked by the sandbox policy",
                }
            )
            continue
        module_name = f"videoflow_plugin_{manifest['id']}".replace("-", "_").replace(".", "_")
        try:
            spec = importlib.util.spec_from_file_location(module_name, entry)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load {entry}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            loaded.append({**manifest, "loaded": True})
        except Exception as exc:
            loaded.append({**manifest, "loaded": False, "error": str(exc)})
    return loaded


def set_plugin_enabled(plugin_id: str, enabled: bool) -> dict[str, object]:
    root = plugins_dir()
    for directory in root.iterdir() if root.is_dir() else []:
        manifest_path = directory / "plugin.json"
        if not manifest_path.is_file():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if payload.get("id") != plugin_id:
            continue
        payload["enabled"] = enabled
        manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return {**payload, "path": str(directory)}
    raise ValueError(f"Unknown plugin: {plugin_id}")


def plugin_summary() -> dict[str, Any]:
    items = list_plugins()
    return {
        "ok": True,
        "plugins": items,
        "enabled": sum(1 for item in items if item.get("enabled")),
        "loaded": sum(1 for item in items if item.get("entry_exists")),
    }
