"""System status, doctor, support bundle, backup, restore, and maintenance routes."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from videoflow import __version__
from videoflow.application.database import backup as backup_database
from videoflow.application.database import last_error as database_error
from videoflow.application.database import metrics as database_metrics
from videoflow.application.database import restore as restore_database
from videoflow.application.models import list_models
from videoflow.application.providers import list_providers
from videoflow.application.service_definitions import list_definitions
from videoflow.application.services import server_log_path
from videoflow.application.settings import env_overrides, load_settings, settings_error
from videoflow.bootstrap import BootstrapRequest
from videoflow.domain.errors import PathNotFoundError, VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.engine.maintenance import prune_output
from videoflow.runtime import allowed_roots, find_binary, portable_home


class MaintenancePruneRequest(BaseModel):
    output: str = Field(min_length=1)
    keep_days: int = Field(default=14, ge=1, le=3650)
    keep_steps: int = Field(default=200, ge=1, le=10000)
    keep_runs: int = Field(default=30, ge=1, le=1000)
    include_global_cache: bool = False
    cache_days: int = Field(default=30, ge=1, le=3650)
    cache_max_mb: int = Field(default=512, ge=1, le=100000)
    dry_run: bool = False


def register_system_routes(app: FastAPI) -> None:
    """Register system status, doctor, support bundle, backup, restore, and maintenance routes."""

    @app.post("/api/v1/maintenance/backup")
    def maintenance_backup() -> dict[str, object]:
        from videoflow.application.backups import scheduled_backup

        try:
            target = scheduled_backup()
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"ok": False, "code": "backup_failed", "message": str(exc)},
            ) from exc
        return {"ok": True, "backup": str(target)}

    @app.post("/api/v1/maintenance/prune")
    def maintenance_prune(request: MaintenancePruneRequest) -> dict[str, object]:
        resolved = resolve_allowed(Path(request.output), allowed_roots())
        if not resolved.is_dir():
            raise PathNotFoundError(f"Output directory does not exist: {resolved}")
        result = prune_output(
            resolved,
            keep_days=request.keep_days,
            keep_steps=request.keep_steps,
            keep_runs=request.keep_runs,
            dry_run=request.dry_run,
        )
        if request.include_global_cache:
            from videoflow.steps.cache import prune_cache

            result["global_cache"] = prune_cache(
                max_age_days=request.cache_days,
                max_bytes=request.cache_max_mb * 1024 * 1024,
                dry_run=request.dry_run,
            )
        return result

    @app.post("/api/v1/system/restart")
    def system_restart(request: Request) -> dict[str, object]:
        server = getattr(request.app.state, "uvicorn_server", None)
        if server is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "code": "service_control_unavailable",
                    "message": "Service controls are only available in the desktop server.",
                },
            )
        request.app.state.restart_requested = True
        server.should_exit = True
        return {"ok": True, "action": "restart"}

    @app.post("/api/v1/system/shutdown")
    def system_shutdown(request: Request) -> dict[str, object]:
        server = getattr(request.app.state, "uvicorn_server", None)
        if server is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "code": "service_control_unavailable",
                    "message": "Service controls are only available in the desktop server.",
                },
            )
        request.app.state.restart_requested = False
        server.should_exit = True
        return {"ok": True, "action": "shutdown"}

    @app.post("/api/v1/system/bootstrap/opencode")
    def system_bootstrap_opencode(request: BootstrapRequest) -> dict[str, object]:
        from videoflow.bootstrap import bootstrap_opencode_workspace

        try:
            result = bootstrap_opencode_workspace(request)
        except (ValueError, VideoFlowError) as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "ok": False,
                    "code": "bootstrap_failed",
                    "message": str(exc),
                },
            ) from exc
        payload = result.model_dump(mode="json")
        payload["ok"] = True
        return payload

    @app.get("/api/v1/system/opencode/mcp-health")
    def system_mcp_health() -> dict[str, object]:
        from vf_shared.compute.config import load_gpu_config

        from videoflow.application.opencode_config import (
            executable,
            global_config_path,
            mcp_launcher_path,
        )
        from videoflow.bootstrap import global_videoflow_servers

        path = global_config_path()
        global_servers = global_videoflow_servers()
        configured: list[dict[str, object]] = []
        warnings: list[str] = []
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                payload = {}
                warnings.append(f"{path} is not plain JSON")
            servers = (payload.get("mcp") or {}).get("servers") if isinstance(payload, dict) else {}
            if isinstance(servers, dict):
                for name, block in servers.items():
                    if not isinstance(block, dict):
                        continue
                    command = block.get("command")
                    first = str(command[0]) if isinstance(command, list) and command else ""
                    exists = bool(first) and Path(first).expanduser().is_file()
                    configured.append(
                        {
                            "name": name,
                            "command": command,
                            "exists": exists,
                            "videoflow": str(name) in global_servers,
                        }
                    )
                    if str(name) in global_servers and not exists:
                        warnings.append(
                            f"global MCP '{name}' points to a missing executable: {first}"
                        )
        launcher = mcp_launcher_path()
        gpu = load_gpu_config()
        if global_servers:
            warnings.append(
                "VideoFlow is registered in the global OpenCode config. "
                "Prefer workspace-local installation."
            )
        return {
            "ok": True,
            "global_path": str(path),
            "global_videoflow_servers": global_servers,
            "configured": configured,
            "launcher": str(launcher),
            "launcher_exists": launcher.is_file(),
            "executable": executable(),
            "worker_url": gpu.worker_url,
            "worker_source": gpu.source,
            "videoflow_home": os.environ.get("VIDEOWFLOW_HOME", ""),
            "warnings": warnings,
        }

    @app.post("/api/v1/system/opencode/cleanup-global")
    def system_cleanup_global_mcp() -> dict[str, object]:
        from videoflow.bootstrap import remove_global_videoflow_servers

        result = remove_global_videoflow_servers()
        result["ok"] = bool(result.get("ok"))
        return result

    @app.get("/api/v1/system/doctor")
    def system_doctor() -> dict[str, object]:
        from videoflow.application.models import list_models
        from videoflow.runtime import ui_dir
        from videoflow.steps.cache import cache_dir

        checks: dict[str, object] = {
            "version": __version__,
            "home": str(portable_home()),
            "allowed_roots": [str(item) for item in allowed_roots()],
        }
        ok = True
        for name in ("ffmpeg", "ffprobe"):
            path = find_binary(name)
            entry: dict[str, object] = {"path": path, "found": path is not None}
            if path:
                completed = subprocess.run(
                    [path, "-version"], capture_output=True, text=True, check=False
                )
                entry["version"] = completed.stdout.splitlines()[0] if completed.stdout else ""
                entry["exit_code"] = completed.returncode
                ok = ok and completed.returncode == 0
            else:
                ok = False
            checks[name] = entry
        home = portable_home()
        try:
            home.mkdir(parents=True, exist_ok=True)
            probe = home / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checks["home_writable"] = True
        except OSError as exc:
            checks["home_writable"] = False
            checks["home_error"] = str(exc)
            ok = False
        cache = cache_dir()
        checks["cache_bytes"] = (
            sum(item.stat().st_size for item in cache.rglob("*") if item.is_file())
            if cache.is_dir()
            else 0
        )
        checks["models"] = [
            {"id": item["id"], "installed": item["installed"]} for item in list_models()
        ]
        checks["ui"] = str(ui_dir()) if ui_dir() else None
        try:
            usage = shutil.disk_usage(home)
            free_bytes, total_bytes = usage.free, usage.total
        except OSError:
            free_bytes = total_bytes = 0
        checks["disk"] = {
            "free_bytes": free_bytes,
            "total_bytes": total_bytes,
        }
        ffmpeg = find_binary("ffmpeg")
        if ffmpeg:
            codecs = subprocess.run(
                [ffmpeg, "-hide_banner", "-codecs"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            filters = subprocess.run(
                [ffmpeg, "-hide_banner", "-filters"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            checks["ffmpeg_capabilities"] = {
                "libx264": "libx264" in codecs,
                "aac": "aac" in codecs,
                "ass": " ass " in filters,
                "lut3d": "lut3d" in filters,
                "ebur128": "ebur128" in filters,
                "loudnorm": "loudnorm" in filters,
            }
        try:
            import ctranslate2

            checks["cuda_devices"] = int(ctranslate2.get_cuda_device_count())
        except Exception:
            checks["cuda_devices"] = 0
        try:
            import onnxruntime

            checks["onnx_providers"] = list(onnxruntime.get_available_providers())
        except Exception:
            checks["onnx_providers"] = []
        try:
            import sqlite3

            connection = sqlite3.connect(portable_home() / "videoflow.db")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            connection.close()
            checks["database"] = {
                "integrity": integrity,
                "ok": integrity == "ok",
                "error": database_error(),
            }
            ok = ok and integrity == "ok" and not database_error()
        except Exception as exc:
            checks["database"] = {"integrity": "unavailable", "ok": False, "error": str(exc)}
        settings = load_settings()
        error = settings_error()
        checks["settings"] = {
            "file": str(portable_home() / "settings.json"),
            "valid": not error,
            "error": error,
            "locale": settings.runtime.locale,
            "theme": settings.ui.theme,
        }
        ok = ok and not error
        checks["providers"] = len(list_providers())
        checks["service_definitions"] = len(list_definitions())
        try:
            from videoflow.application.capabilities import feature_matrix

            checks["feature_matrix"] = feature_matrix()
        except Exception as exc:  # noqa: BLE001 - diagnostics must not break doctor
            checks["feature_matrix"] = []
            checks["feature_matrix_error"] = str(exc)
        return {"ok": ok, "checks": checks}

    @app.get("/api/v1/metrics/cost")
    def cost_metrics() -> dict[str, object]:
        from videoflow.application.cost import snapshot

        return {"ok": True, "usage": snapshot()}

    @app.get("/api/v1/system/support-bundle")
    def system_support_bundle() -> StreamingResponse:
        buffer = io.BytesIO()
        settings = load_settings().model_dump(mode="json")
        redacted_env = {key: "***" for key in env_overrides()}
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("doctor.json", json.dumps(system_doctor(), indent=2) + "\n")
            bundle.writestr("settings.json", json.dumps(settings, indent=2) + "\n")
            bundle.writestr("environment.json", json.dumps(redacted_env, indent=2) + "\n")
            bundle.writestr(
                "providers.json",
                json.dumps(list_providers(), indent=2) + "\n",
            )
            bundle.writestr("models.json", json.dumps(list_models(), indent=2) + "\n")
            bundle.writestr(
                "service-definitions.json",
                json.dumps(
                    [item.model_dump(mode="json") for item in list_definitions()],
                    indent=2,
                )
                + "\n",
            )
            log = server_log_path()
            if log.is_file():
                bundle.write(log, "server.log")
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=videoflow-support.zip"},
        )

    @app.post("/api/v1/system/restore")
    async def system_restore(request: Request) -> dict[str, object]:
        body = await request.body()
        if not body:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "empty_backup", "message": "ZIP body is empty"},
            )
        temp = portable_home() / "backups" / "restore-upload.zip"
        temp.parent.mkdir(parents=True, exist_ok=True)
        temp.write_bytes(body)
        try:
            result = restore_database(temp)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "invalid_backup", "message": str(exc)},
            ) from exc
        return result

    @app.get("/api/v1/system/metrics")
    def system_metrics() -> dict[str, object]:
        return database_metrics()

    @app.get("/api/v1/system/backup")
    def system_backup() -> FileResponse:
        target = portable_home() / "backups" / "videoflow-backup.zip"
        backup_database(target)
        return FileResponse(
            target,
            media_type="application/zip",
            filename="videoflow-backup.zip",
        )

    @app.post("/api/v1/system/choose-folder")
    def system_choose_folder(payload: dict[str, object] | None = None) -> dict[str, object]:
        initial = str((payload or {}).get("initial") or "").strip()
        try:
            selected = _choose_folder(initial)
        except Exception as exc:  # noqa: BLE001 - report picker failures cleanly
            raise HTTPException(
                status_code=400,
                detail={
                    "ok": False,
                    "code": "folder_picker_unavailable",
                    "message": str(exc),
                },
            ) from exc
        if not selected:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "path": selected}

    @app.get("/api/v1/system/browse-folders")
    def system_browse_folders(path: str = "") -> dict[str, object]:
        try:
            return {"ok": True, **_browse_folders(path)}
        except Exception as exc:  # noqa: BLE001 - report listing failures cleanly
            raise HTTPException(
                status_code=400,
                detail={
                    "ok": False,
                    "code": "folder_browser_unavailable",
                    "message": str(exc),
                },
            ) from exc

    @app.get("/api/v1/system")
    def system() -> dict[str, object]:
        return {
            "ok": True,
            "version": __version__,
            "home": str(portable_home()),
            "allowed_roots": [str(item) for item in allowed_roots()],
            "ffmpeg": find_binary("ffmpeg"),
            "ffprobe": find_binary("ffprobe"),
            "settings_error": settings_error(),
            "database_error": database_error(),
        }


def _is_windows() -> bool:
    return os.name == "nt"


def _folder_roots() -> list[str]:
    roots: list[str] = []
    for candidate in (*allowed_roots(), portable_home(), Path.home()):
        try:
            resolved = Path(candidate).expanduser().resolve()
        except OSError:
            continue
        text = str(resolved)
        if resolved.is_dir() and text not in roots:
            roots.append(text)
    if _is_windows():
        drives = getattr(os, "listdrives", None)
        values = list(drives()) if callable(drives) else []
        if not values:
            values = [
                f"{letter}:\\"
                for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                if Path(f"{letter}:\\").is_dir()
            ]
        for drive in values:
            text = str(Path(str(drive)))
            if text not in roots and Path(text).is_dir():
                roots.append(text)
    return roots


def _browse_folders(path: str = "") -> dict[str, object]:
    roots = _folder_roots()
    fallback = Path(roots[0]) if roots else Path.cwd()
    candidate = Path(path).expanduser() if str(path or "").strip() else fallback
    try:
        candidate = candidate.resolve()
    except OSError:
        candidate = fallback.resolve()
    while not candidate.is_dir() and candidate.parent != candidate:
        candidate = candidate.parent
    if not candidate.is_dir():
        candidate = fallback.resolve()
    try:
        entries = sorted(
            (item for item in candidate.iterdir() if item.is_dir()),
            key=lambda item: item.name.casefold(),
        )
    except OSError as exc:
        raise RuntimeError(f"Cannot list {candidate}: {exc}") from exc
    parent = candidate.parent if candidate.parent != candidate else None
    return {
        "path": str(candidate),
        "parent": str(parent) if parent is not None else None,
        "roots": roots,
        "directories": [
            {"name": item.name, "path": str(item)} for item in entries[:1000]
        ],
        "truncated": len(entries) > 1000,
    }


def _choose_folder_windows(initial: str = "") -> str | None:
    """Open the native Windows folder dialog through Windows PowerShell."""

    executable = shutil.which("powershell") or shutil.which("pwsh")
    if executable is None:
        return None
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$dialog.Description = 'Select the VideoFlow workspace folder';"
        "$dialog.ShowNewFolderButton = $true;"
        "if ($env:VF_INITIAL_DIR -and (Test-Path -LiteralPath $env:VF_INITIAL_DIR)) {"
        " $dialog.SelectedPath = $env:VF_INITIAL_DIR };"
        "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {"
        " [Console]::Out.Write($dialog.SelectedPath) }"
    )
    environment = dict(os.environ)
    environment["VF_INITIAL_DIR"] = initial
    try:
        completed = subprocess.run(
            [executable, "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _choose_folder(initial: str = "") -> str:
    """Open a native folder picker in the desktop session."""

    if _is_windows():
        selected = _choose_folder_windows(initial)
        if selected is not None:
            return selected
    if not _is_windows():
        if shutil.which("zenity"):
            argv = ["zenity", "--file-selection", "--directory"]
            if initial:
                argv.extend(["--filename", initial])
            completed = subprocess.run(
                argv, capture_output=True, text=True, check=False, timeout=300
            )
            if completed.returncode == 0:
                return completed.stdout.strip()
            return ""
        if shutil.which("kdialog"):
            argv = ["kdialog", "--getexistingdirectory", initial or str(Path.home())]
            completed = subprocess.run(
                argv, capture_output=True, text=True, check=False, timeout=300
            )
            return completed.stdout.strip() if completed.returncode == 0 else ""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # noqa: BLE001 - optional desktop dependency
        raise RuntimeError(
            "No folder picker is available; type the path manually."
        ) from exc
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(initialdir=initial or str(Path.home()))
    root.destroy()
    return str(selected or "")
