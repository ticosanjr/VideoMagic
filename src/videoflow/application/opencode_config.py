"""OpenCode configuration blocks and profile definitions."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

PROFILES: dict[str, list[str]] = {
    "opencode": ["core"],
    "core": ["core"],
    "decupagem": ["core"],
    "broll": ["core"],
    "audio": ["core"],
    "vision": ["core"],
    "full": ["core"],
}


@lru_cache(maxsize=1)
def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False)) or not (project_root() / "packages").is_dir()


def _current_executable() -> str:
    """Return a stable executable path, not the disposable AppImage mount."""

    appimage = os.environ.get("APPIMAGE", "").strip()
    if appimage:
        candidate = Path(appimage).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
    if is_packaged():
        found = shutil.which("videoflow")
        if found:
            return str(Path(found).resolve())
    return ""


def mcp_launcher_path() -> Path:
    """Stable launcher that survives AppImage mount churn and version swaps."""

    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "VideoFlow" / "videoflow-mcp.cmd"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "videoflow" / "bin" / "videoflow"


def ensure_mcp_launcher() -> str:
    """Write a stable wrapper around the current packaged executable."""

    if not (getattr(sys, "frozen", False) or os.environ.get("APPIMAGE")):
        return ""
    target = _current_executable()
    if not target:
        return ""
    launcher = mcp_launcher_path()
    try:
        launcher.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            text = f'@echo off\r\n"{target}" %*\r\n'
        else:
            text = "#!/bin/sh\nexec " + shlex.quote(target) + ' "$@"\n'
        launcher.write_text(text, encoding="utf-8", newline="")
        if not sys.platform.startswith("win"):
            launcher.chmod(0o755)
        return str(launcher)
    except OSError:
        return target


def executable() -> str:
    if is_packaged():
        return (
            ensure_mcp_launcher()
            or _current_executable()
            or str(Path(sys.executable).resolve())
        )
    return str(Path(sys.executable).resolve())


def _environment(
    workspace_root: str,
    *,
    prompts: bool,
    videoflow_home: str = "",
) -> dict[str, str]:
    environment = {"VF_WORKSPACE_ROOT": workspace_root}
    if videoflow_home.strip():
        environment["VIDEOWFLOW_HOME"] = str(
            Path(videoflow_home).expanduser().resolve()
        )
    if not prompts:
        environment["VF_MCP_PROMPTS"] = "0"
    return environment


def server_block(
    name: str,
    *,
    workspace_root: str,
    prompts: bool = True,
    videoflow_home: str = "",
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
            "environment": _environment(
                workspace_root,
                prompts=prompts,
                videoflow_home=videoflow_home,
            ),
            "timeout": {"startup": 120000, "catalog": 120000},
        }
    raise ValueError(f"Unknown MCP server: {name}")


def build_config(
    profile: str,
    *,
    workspace_root: str,
    prompts: bool = True,
    videoflow_home: str = "",
) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown MCP profile: {profile}")
    return {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "timeout": {"startup": 120000, "catalog": 120000},
            "servers": {
                name: server_block(
                    name,
                    workspace_root=workspace_root,
                    prompts=prompts,
                    videoflow_home=videoflow_home,
                )
                for name in PROFILES[profile]
            },
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
    for key, value in (generated.get("mcp") or {}).items():
        if key != "servers":
            existing_mcp.setdefault(key, value)
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
    "ensure_mcp_launcher",
    "executable",
    "global_config_path",
    "is_packaged",
    "mcp_launcher_path",
    "merge_config",
    "project_root",
    "server_block",
]
