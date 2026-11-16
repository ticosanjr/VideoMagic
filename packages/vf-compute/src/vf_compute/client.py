"""Minimal synchronous client for a VideoFlow GPU worker."""

from __future__ import annotations

import os
import re
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from vf_compute.models import JobStatus, WorkerHealth

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]{1,200}$")
TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled", "canceled", "done", "error"})


class GPUWorkerError(RuntimeError):
    """Raised when a GPU worker request fails or returns an invalid payload."""


def _safe_segment(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not _SEGMENT_RE.fullmatch(value)
        or value in {".", ".."}
    ):
        raise ValueError(f"invalid {field}: {value!r}")
    return value


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise GPUWorkerError("worker returned invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise GPUWorkerError("worker returned a non-object JSON payload")
    return {str(key): value for key, value in payload.items()}


def _atomic_write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


class GPUWorkerClient:
    """Synchronous HTTP client for a GPU worker.

    The client only talks to the configured base URL. Job ids, artifact names
    and route fragments are validated before they are placed in a URL, and
    downloads always target a caller-provided local path.
    """

    def __init__(
        self,
        base_url: str,
        token: str = "",
        timeout: float = 30.0,
        *,
        transport: httpx.BaseTransport | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = float(timeout)
        self._headers = {"X-VF-Token": token} if token else {}
        self._http = http_client or httpx.Client(
            timeout=self.timeout,
            transport=transport,
            headers=self._headers,
        )

    def __enter__(self) -> GPUWorkerClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = self._http.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers,
                timeout=timeout if timeout is not None else self.timeout,
                **kwargs,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GPUWorkerError(
                f"worker request failed: {exc.response.status_code} {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise GPUWorkerError(f"worker request failed: {exc}") from exc
        return response

    def health(self, timeout: float | None = None) -> WorkerHealth:
        """Fetch worker health."""

        response = self._request("GET", "/health", timeout=timeout)
        return WorkerHealth.from_payload(_json_object(response))

    def upload_artifact(self, content: bytes | bytearray | memoryview | str | Path) -> str:
        """Upload bytes or a local file and return the worker artifact id."""

        if isinstance(content, (bytes, bytearray, memoryview)):
            data = bytes(content)
            name = "artifact.bin"
        else:
            source = Path(content)
            if not source.is_file():
                raise FileNotFoundError(f"artifact not found: {source}")
            data = source.read_bytes()
            name = source.name

        response = self._request("POST", "/artifacts", files={"file": (name, data)})
        payload = _json_object(response)
        artifact_id = payload.get("artifact_id") or payload.get("id")
        if not artifact_id:
            raise GPUWorkerError("worker did not return an artifact id")
        return str(artifact_id)

    def submit(
        self,
        capability: str,
        params: Mapping[str, Any] | None = None,
        inputs: list[str] | None = None,
        *,
        shared_root: str | None = None,
        shared_inputs: list[str] | None = None,
    ) -> str:
        """Submit a job to ``POST /jobs/{capability}`` and return its job id.

        When ``shared_root`` or ``shared_inputs`` is provided the request is
        marked ``shared=true`` and includes the relative paths under both
        ``input_paths`` and ``shared_inputs`` so workers can mount the
        workspace directly.
        """

        if not capability:
            raise ValueError("capability is required")
        clean_capability = _safe_segment(capability, "capability")
        shared = shared_root is not None or bool(shared_inputs)
        body: dict[str, Any] = {
            "params": dict(params or {}),
            "inputs": list(inputs or []),
            "shared": shared,
        }
        if shared:
            input_paths = list(shared_inputs or [])
            body["shared_inputs"] = input_paths
            body["input_paths"] = input_paths

        response = self._request(
            "POST", f"/jobs/{quote(clean_capability, safe='')}", json=body
        )
        payload = _json_object(response)
        job_id = payload.get("job_id") or payload.get("id")
        if not job_id:
            raise GPUWorkerError("worker did not return a job id")
        return str(job_id)

    def status(self, job_id: str) -> JobStatus:
        """Fetch one job status."""

        clean_id = _safe_segment(job_id, "job id")
        response = self._request("GET", f"/jobs/{quote(clean_id, safe='')}")
        return JobStatus.from_payload(_json_object(response), job_id=clean_id)

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

    def download(self, job_id: str, name: str, target: str | Path) -> Path:
        """Download a named job artifact to a local path."""

        clean_id = _safe_segment(job_id, "job id")
        clean_name = _safe_segment(name, "artifact name")
        destination = Path(target)
        response = self._request(
            "GET",
            f"/jobs/{quote(clean_id, safe='')}/artifact/{quote(clean_name, safe='')}",
        )
        _atomic_write(destination, response.content)
        return destination


__all__ = ["GPUWorkerClient", "GPUWorkerError", "TERMINAL_STATES"]
