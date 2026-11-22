"""Job submission, waiting and shared-transport fallbacks."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from vf_shared.compute.execution import ExecutionRecord, now_iso

from .router_common import _shared_relative, _valid_shared_file


class RouterSubmitMixin:
    """Submit capabilities and normalize worker results."""

    def submit(
        self,
        capability: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        """Submit a capability job, wait, and fetch its artifacts.

        Shared mount is preferred when configured, but a failed or empty shared
        output falls back to HTTP automatically. The result always reports the
        transport and whether the job was degraded.
        """

        body = dict(payload or {})
        started_at = now_iso()
        started = time.perf_counter()
        decision = self.decide(capability, int(body.get("required_vram_mb") or 0))
        if not decision.is_remote:
            raise RuntimeError(decision.reason)
        params = body.get("params")
        if not isinstance(params, dict):
            params = {
                key: value
                for key, value in body.items()
                if key not in {"inputs", "shared_inputs", "timeout_sec"}
            }
        raw_inputs = [str(item) for item in body.get("inputs", []) or []]
        if not raw_inputs and body.get("input"):
            raw_inputs = [str(body["input"])]
        shared_inputs = [str(item) for item in body.get("shared_inputs", []) or []]
        shared_outputs = [str(item) for item in body.get("shared_outputs", []) or []]
        body_shared_root = str(body.get("shared_root") or "") or ""
        shared_root = body_shared_root
        shared_local_root = str(
            body.get("shared_local_root") or self.shared_local_root or ""
        )
        health = self._health
        if not shared_root and health is not None and health.shared_root:
            shared_root = str(health.shared_root)
        transport_reason = ""
        shared_mode = (
            self.transport in {"auto", "shared"}
            and bool(shared_root and shared_local_root)
        )
        upload_raw = raw_inputs
        if shared_mode:
            upload_raw = []
            mapped: list[str] = []
            for item in raw_inputs:
                relative = _shared_relative(shared_local_root, item)
                if relative:
                    mapped.append(relative)
                else:
                    upload_raw.append(item)
            for relative in mapped:
                if relative not in shared_inputs:
                    shared_inputs.append(relative)
        elif self.transport == "shared":
            transport_reason = (
                "shared transport requested but VF_GPU_SHARED_LOCAL_ROOT or the "
                "worker shared root is missing; used HTTP"
            )
        reset_transfer = getattr(self.client, "reset_transfer_stats", None)
        if callable(reset_transfer):
            reset_transfer()
        inputs = self._prepare_remote_inputs(upload_raw)
        shared_placeholders: dict[str, str] = {}
        if shared_mode:
            base = len(inputs)
            for index, relative in enumerate(shared_inputs):
                try:
                    local = (Path(shared_local_root) / relative).resolve()
                except (OSError, ValueError):
                    continue
                shared_placeholders[str(local)] = f"__VF_INPUT_{base + index}__"
        params = self._prepare_remote_params(params, inputs, shared_placeholders)
        share_remote_root = shared_root if (shared_mode or body_shared_root) else ""
        submit_kwargs: dict[str, Any] = {
            "params": params,
            "inputs": inputs,
            "shared_inputs": shared_inputs if share_remote_root else [],
            "shared_outputs": shared_outputs,
            "shared_root": share_remote_root or None,
        }
        try:
            job_id = self.client.submit(
                capability,
                priority=int(body.get("priority") or 0),
                **submit_kwargs,
            )
        except TypeError:
            # Older workers and test doubles do not accept the priority keyword.
            job_id = self.client.submit(capability, **submit_kwargs)
        status = self.client.wait(
            job_id,
            timeout=float(body.get("timeout_sec") or timeout),
        )
        if not status.ok:
            raise RuntimeError(
                f"remote job {job_id} ended in {status.state}: {status.error or status.message}"
            )
        if not status.artifacts:
            raise RuntimeError(f"remote job {job_id} returned no artifacts")

        degraded = bool(transport_reason)
        degraded_reason = transport_reason
        if (
            shared_root
            and status.shared_artifacts
            and len(status.shared_artifacts) == len(shared_outputs)
        ):
            shared_paths = [
                Path(shared_root) / relative
                for relative in status.shared_artifacts
            ]
            if all(_valid_shared_file(path) for path in shared_paths):
                elapsed = time.perf_counter() - started
                execution = ExecutionRecord(
                    run_id=job_id,
                    capability=capability,
                    execution_node=decision.execution_node,
                    device="remote_gpu",
                    degraded=False,
                    started_at=started_at,
                    finished_at=now_iso(),
                    elapsed_sec=elapsed,
                )
                return {
                    "path": str(shared_paths[0]),
                    "paths": [str(path) for path in shared_paths],
                    "job_id": job_id,
                    "execution_node": decision.execution_node,
                    "artifacts": list(status.artifacts),
                    "shared_artifacts": list(status.shared_artifacts),
                    "shared_inputs": list(shared_inputs),
                    "transport": "shared_mount",
                    "transfer": self._transfer_summary(),
                    "degraded": bool(transport_reason),
                    "degraded_reason": transport_reason,
                    "execution": execution.to_dict(),
                }
            degraded = True
            degraded_reason = "shared artifact missing or empty; downloaded over HTTP"
        elif shared_root and shared_outputs:
            degraded = True
            degraded_reason = status.shared_error or "shared output was not produced"
        elif status.shared_error:
            degraded = True
            degraded_reason = status.shared_error

        manifest: list[dict[str, Any]] = []
        manifest_reader = getattr(self.client, "artifact_manifest", None)
        if callable(manifest_reader):
            try:
                manifest = manifest_reader(job_id)
            except Exception:  # noqa: BLE001 - manifest is an optimization
                manifest = []
        target_dir = Path(tempfile.mkdtemp(prefix="vf-remote-"))
        download_all = getattr(self.client, "download_all", None)
        if callable(download_all):
            paths = download_all(
                job_id,
                list(status.artifacts),
                target_dir,
                manifest=manifest,
            )
        else:
            name = status.artifacts[0]
            paths = [self.client.download(job_id, name, target_dir / Path(name).name)]
        elapsed = time.perf_counter() - started
        execution = ExecutionRecord(
            run_id=job_id,
            capability=capability,
            execution_node=decision.execution_node,
            device="remote_gpu",
            degraded=degraded,
            degraded_reason=degraded_reason,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=elapsed,
        )
        return {
            "path": str(paths[0]),
            "paths": [str(path) for path in paths],
            "job_id": job_id,
            "execution_node": decision.execution_node,
            "artifacts": list(status.artifacts),
            "shared_artifacts": list(status.shared_artifacts),
            "shared_inputs": list(shared_inputs),
            "transport": "http_fallback" if degraded else "http",
            "transfer": self._transfer_summary(),
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "execution": execution.to_dict(),
        }
