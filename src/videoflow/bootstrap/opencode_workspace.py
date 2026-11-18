"""Generate an OpenCode workspace wired to VideoFlow MCP servers."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow import __version__
from videoflow.application.opencode_config import (
    build_config,
    global_config_path,
    merge_config,
)
from videoflow.application.settings import load_settings, save_settings
from videoflow.application.storage import atomic_write_text
from videoflow.application.style_catalog import StyleCatalog
from videoflow.application.workflow_catalog import WorkflowCatalog
from videoflow.runtime import find_binary

_MANAGED_START = "<!-- videoflow:opencode:start -->"
_MANAGED_END = "<!-- videoflow:opencode:end -->"
_MANAGED_RE = re.compile(
    re.escape(_MANAGED_START) + r".*?" + re.escape(_MANAGED_END),
    re.DOTALL,
)


class BootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_dir: str = Field(min_length=1)
    mcp_profile: Literal["opencode", "core", "decupagem", "broll", "audio", "vision", "full"] = (
        "opencode"
    )
    register_global_opencode: bool = False
    overwrite: bool = False
    include_sample_project: bool = False
    register_root: bool = True
    prompts: bool = False
    workflow_ids: list[str] = Field(default_factory=list)
    style_ids: list[str] = Field(default_factory=list)


class BootstrapResult(BaseModel):
    status: Literal["ok", "warning"] = "ok"
    target_dir: str
    created_files: list[str] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)
    copied_styles: list[str] = Field(default_factory=list)
    copied_workflows: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    launch_command: str = ""
    sample_project: dict[str, object] = Field(default_factory=dict)
    registered_root: bool = False
    warnings: list[str] = Field(default_factory=list)


def templates_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "opencode"


def _backup(path: Path) -> Path | None:
    if not path.is_file():
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    target = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, target)
    return target


def _merge_json_file(
    path: Path,
    generated: dict[str, object],
    *,
    overwrite: bool,
    warnings: list[str],
) -> None:
    existing: dict[str, object] | None = {}
    backed_up = False
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            existing = payload if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            if not overwrite:
                warnings.append(
                    f"{path} is not plain JSON; left unchanged (comment/JSONC not supported)"
                )
                return
            _backup(path)
            backed_up = True
            warnings.append(f"{path} was invalid JSON; a backup was created")
            existing = {}
    merged = merge_config(existing, generated)
    text = json.dumps(merged, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8", errors="replace") == text:
        return
    if path.is_file() and not backed_up:
        _backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, text)


def _style_list(catalog: StyleCatalog) -> str:
    lines = []
    for item in catalog.list_payload():
        lines.append(
            f"- `{item['style_id']}` — {item['name']} "
            f"({item['aspect_ratio'] or 'auto'}) — `./presets/{item['style_id']}.md`"
        )
    return "\n".join(lines) or "- Nenhum estilo cadastrado."


def _workflow_list(catalog: WorkflowCatalog) -> str:
    lines = []
    for item in catalog.list_payload():
        lines.append(
            f"- `{item['workflow_id']}` — {item['name']} "
            f"({item['aspect_ratio'] or 'auto'}) — "
            f"`./.opencode/workflows/{item['workflow_id']}.md`"
        )
    return "\n".join(lines) or "- Nenhum workflow cadastrado."


def _write_agents(
    path: Path, template: str, catalog: StyleCatalog, workflows: WorkflowCatalog
) -> str:
    body = template.replace("{{VERSION}}", __version__).replace("{{TARGET_DIR}}", str(path.parent))
    body = body.replace("{{STYLE_LIST}}", _style_list(catalog))
    body = body.replace("{{WORKFLOW_LIST}}", _workflow_list(workflows))
    if not path.is_file():
        atomic_write_text(path, body if body.endswith("\n") else body + "\n")
        return "created"
    existing = path.read_text(encoding="utf-8")
    if _MANAGED_START in existing and _MANAGED_END in existing:
        updated = _MANAGED_RE.sub(body.strip(), existing)
        action = "updated"
    else:
        updated = existing.rstrip() + "\n\n" + body.strip() + "\n"
        action = "appended"
    if updated == existing:
        return "unchanged"
    atomic_write_text(path, updated)
    return action


def _copy_template_dir(
    source: Path,
    target: Path,
    *,
    overwrite: bool,
    created: list[str],
    skipped: list[str],
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.glob("*.md")):
        destination = target / path.name
        if destination.exists() and not overwrite:
            skipped.append(str(destination))
            continue
        shutil.copy2(path, destination)
        created.append(str(destination))


def _register_allowed_root(target: Path) -> bool:
    settings = load_settings()
    roots = [str(Path(item).expanduser()) for item in settings.paths.allowed_roots]
    resolved = str(target)
    if resolved in roots:
        return False
    settings.paths.allowed_roots = [*roots, resolved]
    save_settings(settings)
    return True


def _sample_project(target: Path) -> dict[str, object]:
    ffmpeg = find_binary("ffmpeg")
    if ffmpeg is None:
        return {"ok": False, "warning": "ffmpeg is not available"}
    output = target / "projects" / "sample-10s"
    output.mkdir(parents=True, exist_ok=True)
    source = output / "source.mp4"
    if not source.is_file():
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=1280x720:rate=30",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000",
                "-t",
                "10",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(source),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if completed.returncode != 0 or not source.is_file():
            return {
                "ok": False,
                "warning": (completed.stderr or "ffmpeg failed")[-500:],
            }
    from videoflow.adapters.ffmpeg import FFmpegAdapter
    from videoflow.application.projects import init_project

    record, _state = init_project(
        name="Sample 10s",
        output=output,
        sources=[str(source)],
        style_id="canal-rafael-tech",
        adapter=FFmpegAdapter(),
    )
    return {
        "ok": True,
        "project_id": record.project_id,
        "output": record.output,
        "source": str(source),
    }


def bootstrap_opencode_workspace(request: BootstrapRequest) -> BootstrapResult:
    target = Path(request.target_dir).expanduser().resolve(strict=False)
    if target.exists() and not target.is_dir():
        raise ValueError(f"target_dir is not a directory: {target}")
    if target == Path(target.anchor):
        raise ValueError("target_dir must not be a filesystem root")
    target.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    created: list[str] = []
    skipped: list[str] = []
    registered_root = bool(request.register_root and _register_allowed_root(target))

    for relative in (
        ".opencode/skills",
        ".opencode/commands",
        "presets",
        "references",
        "projects",
    ):
        (target / relative).mkdir(parents=True, exist_ok=True)

    workspace_root = str(target / "projects")
    config = build_config(
        request.mcp_profile,
        workspace_root=workspace_root,
        prompts=request.prompts,
    )
    _merge_json_file(
        target / "opencode.json",
        config,
        overwrite=request.overwrite,
        warnings=warnings,
    )
    created.append(str(target / "opencode.json"))

    if request.register_global_opencode:
        _merge_json_file(
            global_config_path(),
            config,
            overwrite=request.overwrite,
            warnings=warnings,
        )

    catalog = StyleCatalog()
    workflows = WorkflowCatalog()
    template = (templates_dir() / "AGENTS.md").read_text(encoding="utf-8")
    action = _write_agents(target / "AGENTS.md", template, catalog, workflows)
    created.append(f"{target / 'AGENTS.md'} ({action})")

    _copy_template_dir(
        templates_dir() / "skills",
        target / ".opencode" / "skills",
        overwrite=request.overwrite,
        created=created,
        skipped=skipped,
    )
    _copy_template_dir(
        templates_dir() / "commands",
        target / ".opencode" / "commands",
        overwrite=request.overwrite,
        created=created,
        skipped=skipped,
    )
    sync = catalog.sync(target, overwrite=request.overwrite)
    if request.style_ids:
        selected = set(request.style_ids)
        sync["copied"] = [item for item in sync.get("copied", []) if Path(item).stem in selected]
    workflow_sync = workflows.sync(
        target,
        overwrite=request.overwrite,
        workflow_ids=request.workflow_ids or None,
    )

    sample: dict[str, object] = {}
    if request.include_sample_project:
        sample = _sample_project(target)
        if not sample.get("ok"):
            warnings.append(str(sample.get("warning") or "sample project failed"))
    result = BootstrapResult(
        status="warning" if warnings else "ok",
        target_dir=str(target),
        created_files=created,
        skipped_files=skipped,
        copied_styles=list(sync.get("copied", [])),
        copied_workflows=list(workflow_sync.get("copied", [])),
        mcp_servers=sorted(
            (config.get("mcp", {}).get("servers") or {}).keys()  # type: ignore[union-attr]
        ),
        launch_command=f'cd "{target}" && opencode',
        sample_project=sample,
        registered_root=registered_root,
        warnings=warnings,
    )
    return result


__all__ = [
    "BootstrapRequest",
    "BootstrapResult",
    "bootstrap_opencode_workspace",
    "templates_dir",
]
