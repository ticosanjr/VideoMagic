from __future__ import annotations

import re
from pathlib import Path

from vf_shared.compute.models import WorkerHealth

ROOT = Path(__file__).resolve().parents[2]
API_TS = ROOT / "ui" / "src" / "lib" / "api.ts"


def _interface_keys(name: str) -> set[str]:
    source = API_TS.read_text(encoding="utf-8")
    match = re.search(
        rf"export interface {name} \{{(.*?)^\}}",
        source,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert match is not None, f"interface {name} not found"
    pattern = r"^\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:"
    return {
        item.group(1)
        for item in re.finditer(pattern, match.group(1), re.MULTILINE)
    }


def test_gpu_worker_status_covers_backend_health_contract() -> None:
    frontend = _interface_keys("GpuWorkerStatus")
    backend = set(WorkerHealth.model_fields) - {"models_loaded"}
    # The UI calls this list ``models``.
    backend.add("models")
    missing = sorted(backend - frontend)
    assert missing == []


def test_gpu_worker_status_covers_progress_and_security_fields() -> None:
    frontend = _interface_keys("GpuWorkerStatus")
    assert {
        "disk_free_mb",
        "min_free_disk_mb",
        "uptime_sec",
        "job_retention_hours",
        "nvenc_error",
        "lan_urls",
        "warmup",
        "current_job",
        "allowed_clients",
        "token_only",
    } <= frontend
