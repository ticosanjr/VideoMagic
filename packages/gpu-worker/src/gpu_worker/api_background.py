"""Warmup, audit, history and periodic maintenance for the worker."""

from __future__ import annotations

import shutil
import threading
import time
from types import SimpleNamespace
from typing import Any

from gpu_worker.gpu import detect_gpu
from gpu_worker.handlers_gpu import warmup_models
from gpu_worker.telemetry import rotate_log as _rotate_log


def install_background(
    app: Any,
    *,
    config: Any,
    store: Any,
    artifacts: Any,
    models: Any,
    runner: Any,
    work_dir: Any,
    maintenance_stop: threading.Event,
    retention_sec: float,
) -> SimpleNamespace:
    warmup_lock = threading.Lock()

    def audit(client: str, path: str, method: str, outcome: str) -> None:
        app.state.audit.append(
            {
                "at": time.time(),
                "client": client,
                "path": path,
                "method": method,
                "outcome": outcome,
            }
        )

    def run_warmup() -> dict[str, Any]:
        with warmup_lock:
            if app.state.warmup.get("running"):
                return dict(app.state.warmup)
            app.state.warmup = {
                "running": True,
                "loaded": [],
                "skipped": [],
                "errors": [],
                "started_at": time.time(),
            }
        result = warmup_models(config, models)
        with warmup_lock:
            app.state.warmup = {
                **result,
                "running": False,
                "finished_at": time.time(),
            }
        return dict(app.state.warmup)

    def sample_history() -> dict[str, Any]:
        gpu = detect_gpu()
        metrics = runner.metrics()
        sample = {
            "at": time.time(),
            "gpu_utilization": gpu.gpu_utilization,
            "vram_free_mb": gpu.vram_free_mb,
            "vram_total_mb": gpu.vram_total_mb,
            "temperature_c": gpu.temperature_c,
            "queue_depth": store.queue_depth(),
            "running": len(metrics.get("current") or []),
            "completed": len(metrics.get("recent") or []),
        }
        app.state.history.append(sample)
        return sample

    def history_loop() -> None:
        while not maintenance_stop.wait(5.0):
            try:
                sample_history()
            except Exception:  # noqa: BLE001 - sampling is advisory
                continue

    def maintenance_loop() -> None:
        while not maintenance_stop.wait(3600.0):
            try:
                for stale_job in store.cleanup_finished(retention_sec):
                    shutil.rmtree(work_dir / "jobs" / stale_job, ignore_errors=True)
                artifacts.cleanup(store.referenced_artifact_ids())
                store.prune_metrics(config.metrics_retention_hours * 3600.0)
                _rotate_log(config)
            except Exception:  # noqa: BLE001 - maintenance must never kill the worker
                continue

    app.state.run_warmup = run_warmup

    def start() -> None:
        sample_history()
        threading.Thread(
            target=history_loop,
            name="gpu-worker-history",
            daemon=True,
        ).start()
        threading.Thread(
            target=maintenance_loop,
            name="gpu-worker-maintenance",
            daemon=True,
        ).start()
        if config.warmup and config.builtin_handlers:
            threading.Thread(
                target=run_warmup,
                name="gpu-worker-warmup",
                daemon=True,
            ).start()

    return SimpleNamespace(
        audit=audit,
        run_warmup=run_warmup,
        sample_history=sample_history,
        start=start,
    )
