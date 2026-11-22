"""Worker job submission, status, wait and maintenance calls."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from .client_common import GPUWorkerError, GPUWorkerUnsupported, _json_object, _safe_segment
from .models import JobStatus


class ClientJobsMixin:
    """Submit jobs and inspect worker state."""

    def submit(
        self,
        capability: str,
        params: Mapping[str, Any] | None = None,
        inputs: list[str] | None = None,
        *,
        shared_root: str | None = None,
        shared_inputs: list[str] | None = None,
        shared_outputs: list[str] | None = None,
        priority: int = 0,
    ) -> str:
        """Submit a job to ``POST /jobs/{capability}`` and return its job id.

        When ``shared_root`` or ``shared_inputs`` is provided the request is
        marked ``shared=true`` and includes the relative paths under both
        ``input_paths`` and ``shared_inputs`` so workers can mount the
        workspace directly. ``shared_outputs`` asks the worker to write results
        into the same mounted workspace.
        """

        if not capability:
            raise ValueError("capability is required")
        clean_capability = _safe_segment(capability, "capability")
        shared = (
            shared_root is not None
            or bool(shared_inputs)
            or bool(shared_outputs)
        )
        body: dict[str, Any] = {
            "params": dict(params or {}),
            "inputs": list(inputs or []),
            "shared": shared,
        }
        if int(priority):
            body["priority"] = max(-100, min(100, int(priority)))
        if shared:
            input_paths = list(shared_inputs or [])
            body["shared_inputs"] = input_paths
            body["input_paths"] = input_paths
            body["shared_outputs"] = list(shared_outputs or [])

        response = self._request(
            "POST", f"/jobs/{quote(clean_capability, safe='')}", json=body
        )
        payload = _json_object(response)
        job_id = payload.get("job_id") or payload.get("id")
        if not job_id:
            raise GPUWorkerError("worker did not return a job id")
        return str(job_id)


    def overview(self, timeout: float | None = None) -> dict[str, Any]:
        response = self._request("GET", "/api/overview", timeout=timeout)
        return _json_object(response)


    def status(self, job_id: str) -> JobStatus:
        """Fetch one job status."""

        clean_id = _safe_segment(job_id, "job id")
        response = self._request("GET", f"/jobs/{quote(clean_id, safe='')}")
        return JobStatus.from_payload(_json_object(response), job_id=clean_id)


    def probe(self) -> dict[str, Any]:
        """Run the worker's real CUDA/NVENC/matte probe."""

        try:
            response = self._request("POST", "/probe")
        except GPUWorkerError as exc:
            if exc.status_code in {404, 405}:
                raise GPUWorkerUnsupported(
                    "worker does not implement /probe",
                    status_code=exc.status_code,
                ) from exc
            raise
        return _json_object(response)


    def unload_models(self, name: str = "") -> dict[str, Any]:
        """Ask the worker to free one model or every loaded model."""

        response = self._request(
            "POST",
            "/models/unload",
            json={"name": str(name or "")},
        )
        return _json_object(response)


    def validate_shared(self, path: str) -> dict[str, Any]:
        """Ask the worker to validate one shared write path."""

        response = self._request(
            "POST",
            "/shared/validate",
            json={"path": str(path or "")},
        )
        return _json_object(response)


    def wait(self, job_id: str, timeout: float = 300.0, poll: float = 0.5) -> JobStatus:
        """Poll until a job reaches a terminal state or ``timeout`` elapses."""

        deadline = time.monotonic() + max(timeout, 0.0)
        delay = max(poll, 0.0)
        last = self.status(job_id)
        while not last.done:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"job {job_id} did not finish within {timeout}s (state={last.state})"
                )
            if delay:
                time.sleep(delay)
            last = self.status(job_id)
        return last
