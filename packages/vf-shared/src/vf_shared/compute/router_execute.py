"""Remote execution and input/parameter preparation."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from vf_shared.compute.execution import ExecutionRecord, now_iso


class RouterExecuteMixin:
    """Run a capability remotely and describe the transfer."""

    def execute(
        self,
        capability: str,
        remote_fn: Any,
        local_fn: Any,
        *,
        required_vram_mb: int = 0,
        fallback_local: bool = True,
    ) -> dict[str, Any]:
        """Run remotely when possible, falling back locally on any failure.

        The return value keeps the caller's payload under ``value`` and records
        the placement, fallback reason, and elapsed time for job telemetry.
        """

        decision = self.decide(capability, required_vram_mb)
        started_at = now_iso()
        if decision.is_remote:
            started = time.perf_counter()
            try:
                value = remote_fn()
            except Exception as exc:  # noqa: BLE001 - fallback is the contract
                self.invalidate()
                if not fallback_local:
                    raise
                reason = f"remote failed: {exc}"
            else:
                elapsed = time.perf_counter() - started
                execution = ExecutionRecord(
                    run_id="",
                    capability=capability,
                    execution_node=decision.execution_node,
                    device="remote_gpu",
                    degraded=False,
                    started_at=started_at,
                    finished_at=now_iso(),
                    elapsed_sec=elapsed,
                )
                return {
                    "value": value,
                    "execution_node": decision.execution_node,
                    "fallback_reason": "",
                    "remote": True,
                    "worker_source": self.worker_source,
                    "degraded": False,
                    "degraded_reason": "",
                    "elapsed_sec": round(elapsed, 4),
                    "execution": execution.to_dict(),
                }
        else:
            health = self.health()
            reason = (
                "windows_gpu_offline_fallback_cpu"
                if self.mode != "local_only" and not health.available
                else decision.reason
            )
        started = time.perf_counter()
        value = local_fn()
        elapsed = time.perf_counter() - started
        degraded = self.mode != "local_only"
        execution = ExecutionRecord(
            run_id="",
            capability=capability,
            execution_node="local",
            device="cpu",
            degraded=degraded,
            degraded_reason=reason,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=elapsed,
        )
        return {
            "value": value,
            "execution_node": "local",
            "fallback_reason": reason,
            "remote": False,
            "worker_source": self.worker_source,
            "degraded": degraded,
            "degraded_reason": reason,
            "elapsed_sec": round(elapsed, 4),
            "execution": execution.to_dict(),
        }


    def _prepare_remote_inputs(self, inputs: list[str]) -> list[str]:
        upload = getattr(self.client, "upload_artifact", None)
        if not callable(upload):
            return inputs
        prepared: list[str | None] = [None] * len(inputs)
        pending: list[tuple[int, str, Path]] = []
        known: dict[str, str] = {}
        for index, item in enumerate(inputs):
            try:
                path = Path(item).expanduser()
                if not path.is_file():
                    prepared[index] = item
                    continue
                resolved = str(path.resolve())
            except OSError:
                prepared[index] = item
                continue
            existing = known.get(resolved)
            if existing is not None:
                prepared[index] = existing
                continue
            pending.append((index, resolved, path))
        if not pending:
            return [item for item in prepared if item is not None]
        if len(pending) > 1 and self.upload_workers > 1:
            with ThreadPoolExecutor(max_workers=self.upload_workers) as pool:
                uploaded = list(pool.map(lambda item: str(upload(item[2])), pending))
        else:
            uploaded = [str(upload(item[2])) for item in pending]
        for (index, resolved, _path), artifact_id in zip(pending, uploaded, strict=True):
            known[resolved] = artifact_id
            prepared[index] = artifact_id
        return [item if item is not None else "" for item in prepared]


    def _prepare_remote_params(
        self,
        params: dict[str, Any],
        inputs: list[str],
        shared_placeholders: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Upload local files referenced by params and replace them by placeholders.

        The worker rewrites ``__VF_INPUT_n__`` to the materialized input path
        before calling the handler, so command templates and Python handlers see
        a real local path on the GPU machine. Files already reachable through a
        shared mount keep their index without an upload.
        """

        upload = getattr(self.client, "upload_artifact", None)
        if not callable(upload):
            return params
        cache: dict[str, str] = dict(shared_placeholders or {})

        def walk(value: Any) -> Any:
            if isinstance(value, str):
                try:
                    path = Path(value).expanduser()
                    if not path.is_file():
                        return value
                    resolved = str(path.resolve())
                except OSError:
                    return value
                placeholder = cache.get(resolved)
                if placeholder is not None:
                    return placeholder
                artifact_id = str(upload(path))
                index = len(inputs)
                inputs.append(artifact_id)
                placeholder = f"__VF_INPUT_{index}__"
                cache[resolved] = placeholder
                return placeholder
            if isinstance(value, dict):
                return {str(key): walk(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [walk(item) for item in value]
            return value

        return walk(params)


    def _transfer_summary(self) -> dict[str, Any]:
        stats = getattr(self.client, "transfer_stats", {}) or {}
        upload_bytes = int(stats.get("upload_bytes") or 0)
        download_bytes = int(stats.get("download_bytes") or 0)
        seconds = float(stats.get("upload_seconds") or 0) + float(
            stats.get("download_seconds") or 0
        )
        return {
            "upload_bytes": upload_bytes,
            "download_bytes": download_bytes,
            "upload_seconds": round(float(stats.get("upload_seconds") or 0), 3),
            "download_seconds": round(float(stats.get("download_seconds") or 0), 3),
            "dedup_uploads": int(stats.get("upload_dedup") or 0),
            "mb_per_sec": round(
                (upload_bytes + download_bytes) / 1_000_000 / max(seconds, 0.001), 3
            ),
        }
