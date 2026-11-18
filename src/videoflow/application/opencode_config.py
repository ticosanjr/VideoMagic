"""OpenCode configuration blocks and profile definitions."""

from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

PROFILES: dict[str, list[str]] = {
    "opencode": ["core", "fetch", "audio", "vision"],
    "core": ["core"],
    "decupagem": ["core"],
    "broll": ["core", "fetch"],
    "audio": ["core", "audio"],
    "vision": ["core", "vision"],
    "full": ["core", "fetch", "audio", "vision"],
}

_DOMAIN_PACKAGES = {
    "fetch": "mcp-fetch",
    "audio": "mcp-audio",
    "vision": "mcp-vision",
}
_DOMAIN_COMMANDS = {
    "fetch": "videoflow-mcp-fetch",
    "audio": "videoflow-mcp-audio",
    "vision": "videoflow-mcp-vision",
}
_DOMAIN_SUBCOMMANDS = {
    "fetch": "mcp-fetch",
    "audio": "mcp-audio",
    "vision": "mcp-vision",
}


@lru_cache(maxsize=1)
def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False)) or not (project_root() / "packages").is_dir()


def executable() -> str:
    return str(Path(sys.executable).resolve())


def _environment(workspace_root: str, *, prompts: bool) -> dict[str, str]:
    environment = {
        "VF_WORKSPACE_ROOT": workspace_root,
        "VIDEOWFLOW_HOME": str(
            Path(workspace_root).expanduser().resolve().parent / "videoflow-data"
        ),
        "VF_COMPUTE_MODE": "${VF_COMPUTE_MODE:-auto}",
        "VF_GPU_WORKER_URL": "${VF_GPU_WORKER_URL:-}",
        "VF_GPU_WORKER_TOKEN": "${VF_GPU_WORKER_TOKEN:-}",
    }
    if not prompts:
        environment["VF_MCP_PROMPTS"] = "0"
    return environment


def server_block(
    name: str,
    *,
    workspace_root: str,
    prompts: bool = True,
) -> dict[str, Any]:
    if name == "core":
        if is_packaged():
            command = [executable(), "mcp"]
        else:
            command = [
                "uv",
                "run",
                "--directory",
                str(project_root()),
                "videoflow-mcp",
            ]
        if not prompts:
            command.append("--no-prompts")
        return {
            "type": "local",
            "command": command,
            "environment": _environment(workspace_root, prompts=prompts),
        }
    if name not in _DOMAIN_PACKAGES:
        raise ValueError(f"Unknown MCP server: {name}")
    if is_packaged():
        command = [executable(), _DOMAIN_SUBCOMMANDS[name]]
    else:
        command = [
            "uv",
            "run",
            "--project",
            str(project_root() / "packages" / _DOMAIN_PACKAGES[name]),
            _DOMAIN_COMMANDS[name],
        ]
    return {
        "type": "local",
        "command": command,
        "environment": _environment(workspace_root, prompts=prompts),
    }


def build_config(
    profile: str,
    *,
    workspace_root: str,
    prompts: bool = True,
) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown MCP profile: {profile}")
    return {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "servers": {
                name: server_block(
                    name,
                    workspace_root=workspace_root,
                    prompts=prompts,
                )
                for name in PROFILES[profile]
            }
        },
    }


def merge_config(existing: dict[str, Any] | None, generated: dict[str, Any]) -> dict[str, Any]:
    """Preserve unrelated OpenCode settings and replace only VideoFlow servers."""

    merged = json.loads(json.dumps(existing or {}))
    merged.setdefault("$schema", generated.get("$schema"))
    existing_mcp = merged.setdefault("mcp", {})
    if not isinstance(existing_mcp, dict):
        existing_mcp = {}
        merged["mcp"] = existing_mcp
    existing_servers = existing_mcp.setdefault("servers", {})
    if not isinstance(existing_servers, dict):
        existing_servers = {}
        existing_mcp["servers"] = existing_servers
    for name, block in (generated.get("mcp", {}).get("servers") or {}).items():
        existing_servers[name] = block
    return merged


def global_config_path() -> Path:
    override = os.environ.get("OPENCODE_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser() / "opencode.json"
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "opencode" / "opencode.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "opencode" / "opencode.json"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "opencode" / "opencode.json"


__all__ = [
    "PROFILES",
    "build_config",
    "executable",
    "global_config_path",
    "is_packaged",
    "merge_config",
    "project_root",
    "server_block",
]
