"""One-click startup support for the portable executable.

The first launch of ``videoflow.exe`` must be useful without a manual models
command. This module starts one daemon thread that installs only the models the
default pipeline needs, and records progress in the shared ``jobs`` table so the
UI and MCP can show what is happening.
"""

from __future__ import annotations

import os
import threading
from typing import Any

from videoflow.application import database
from videoflow.application.clock import now_iso
from videoflow.application.models import (
    install_model,
    installed_path,
    invalidate_model_cache,
)

ESSENTIAL_MODELS = ("silero-vad", "faster-whisper-small")
_DISABLED_VALUES = frozenset({"1", "true", "yes", "on"})

_lock = threading.Lock()
_thread: threading.Thread | None = None


def auto_download_disabled() -> bool:
    """Whether the operator or a headless smoke run disabled model downloads."""

    value = os.environ.get("VIDEOWFLOW_NO_AUTO_DOWNLOAD", "").strip().lower()
    return value in _DISABLED_VALUES


def _record(
    job_id: str,
    model_id: str,
    *,
    status: str,
    progress: int,
    message: str,
    created_at: str,
    started_at: str,
    finished_at: str = "",
) -> None:
    payload: dict[str, Any] = {
        "job_id": job_id,
        "project_id": "",
        "origin": "bootstrap",
        "model_id": model_id,
        "status": status,
        "stage": f"downloading {model_id}",
        "message": message,
        "progress": max(0, min(100, int(progress))),
        "source": model_id,
        "output": "",
        "options": {
            "origin": "bootstrap",
            "model_id": model_id,
            "bootstrap": True,
            "stage": f"downloading {model_id}",
        },
        "created_at": created_at,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    database.upsert_job(job_id, payload)


def _bootstrap(models: tuple[str, ...]) -> None:
    try:
        for model_id in models:
            if installed_path(model_id) is not None:
                continue
            job_id = f"bootstrap-{model_id}"
            created_at = now_iso()
            started_at = created_at
            last = {"percent": -1, "message": ""}

            def report(
                percent: int,
                message: str,
                *,
                job_id: str = job_id,
                model_id: str = model_id,
                created_at: str = created_at,
                started_at: str = started_at,
                last: dict[str, Any] = last,
            ) -> None:
                clamped = max(0, min(100, int(percent)))
                if clamped == last["percent"] and message == last["message"]:
                    return
                last["percent"] = clamped
                last["message"] = message
                _record(
                    job_id,
                    model_id,
                    status="running",
                    progress=clamped,
                    message=message,
                    created_at=created_at,
                    started_at=started_at,
                )

            _record(
                job_id,
                model_id,
                status="running",
                progress=0,
                message=f"Downloading {model_id}",
                created_at=created_at,
                started_at=started_at,
            )
            try:
                result = install_model(model_id, allow_network=True, progress=report)
            except Exception as exc:  # noqa: BLE001 - offline startup must not crash
                _record(
                    job_id,
                    model_id,
                    status="failed",
                    progress=max(0, last["percent"]),
                    message=str(exc) or type(exc).__name__,
                    created_at=created_at,
                    started_at=started_at,
                    finished_at=now_iso(),
                )
                continue
            if not result.get("installed"):
                _record(
                    job_id,
                    model_id,
                    status="failed",
                    progress=max(0, last["percent"]),
                    message=f"Model {model_id} was not installed",
                    created_at=created_at,
                    started_at=started_at,
                    finished_at=now_iso(),
                )
                continue
            _record(
                job_id,
                model_id,
                status="succeeded",
                progress=100,
                message=f"Installed {model_id}",
                created_at=created_at,
                started_at=started_at,
                finished_at=now_iso(),
            )
    finally:
        invalidate_model_cache()


def ensure_essential_models_async(jobs: Any | None = None) -> threading.Thread | None:
    """Start the single bootstrap thread when essential models are missing.

    ``jobs`` is accepted for callers that already own a job manager; progress is
    persisted in the shared database table so every process observes it. The
    function returns quickly and never raises for a download failure.
    """

    global _thread
    if auto_download_disabled():
        return None
    missing = tuple(
        model_id
        for model_id in ESSENTIAL_MODELS
        if installed_path(model_id) is None
    )
    if not missing:
        return None
    with _lock:
        if _thread is not None and _thread.is_alive():
            return _thread
        thread = threading.Thread(
            target=_bootstrap,
            args=(missing,),
            name="videoflow-model-bootstrap",
            daemon=True,
        )
        _thread = thread
        thread.start()
        return thread


def reset_bootstrap_for_tests() -> None:
    """Clear the module-level thread handle without stopping a live download."""

    global _thread
    with _lock:
        _thread = None


__all__ = [
    "ESSENTIAL_MODELS",
    "auto_download_disabled",
    "ensure_essential_models_async",
    "reset_bootstrap_for_tests",
]
